import click
import configparser
import flask
import hashlib
import hmac
import os
import requests
import sys
import time


DEFAULT_SUCCESS_RETURN = 0
DEFAULT_ERROR_RETURN = 10
NO_GH_TOKEN_RETURN = 3
GH_ERROR_RETURN = {
    401: 4,
    404: 5
}
NO_LABELS_SPEC_RETURN = 6
NO_REPOS_SPEC_RETURN = 7
NO_WEBHOOK_SECRET_RETURN = 8

###############################################################################
# GitHub API communicator
###############################################################################


class GitHubError(Exception):

    def __init__(self, response):
        self.status_code = response.status_code
        self.message = response.json().get('message', 'No message provided')

    def __str__(self):
        return 'GitHub: ERROR {}'.format(self.code_message)

    @property
    def code_message(self, sep=' - '):
        return sep.join([str(self.status_code), self.message])


class GitHub:
    GH_API_ENDPOINT = 'https://api.github.com'

    def __init__(self, token, session=None):
        self.token = token
        self.set_session(session)

    def set_session(self, session):
        self.session = session or requests.Session()
        self.session.auth = self._session_auth()

    def _session_auth(self):
        def github_auth(req):
            req.headers = {
                'Authorization': 'token ' + self.token,
                'User-Agent': 'Python/Labelord'
            }
            return req
        return github_auth

    def _get_raising(self, url, expected_code=200):
        response = self.session.get(url)
        if response.status_code != expected_code:
            raise GitHubError(response)
        return response

    def _get_all_data(self, resource):
        """Get all data spread across multiple pages"""
        response = self._get_raising('{}{}?per_page=100&page=1'.format(
            self.GH_API_ENDPOINT, resource
        ))
        yield from response.json()
        while 'next' in response.links:
            response = self._get_raising(response.links['next']['url'])
            yield from response.json()

    def list_repositories(self):
        """Get list of names of accessible repositories (including owner)"""
        data = self._get_all_data('/user/repos')
        return [repo['full_name'] for repo in data]

    def list_labels(self, repository):
        """Get dict of labels with colors for given repository slug"""
        data = self._get_all_data('/repos/{}/labels'.format(repository))
        return {l['name']: str(l['color']) for l in data}

    def create_label(self, repository, name, color, **kwargs):
        """Create new label in given repository"""
        data = {'name': name, 'color': color}
        response = self.session.post(
            '{}/repos/{}/labels'.format(self.GH_API_ENDPOINT, repository),
            json=data
        )
        if response.status_code != 201:
            raise GitHubError(response)

    def update_label(self, repository, name, color, old_name=None, **kwargs):
        """Update existing label in given repository"""
        data = {'name': name, 'color': color}
        response = self.session.patch(
            '{}/repos/{}/labels/{}'.format(
                self.GH_API_ENDPOINT, repository, old_name or name
            ),
            json=data
        )
        if response.status_code != 200:
            raise GitHubError(response)

    def delete_label(self, repository, name, **kwargs):
        """Delete existing label in given repository"""
        response = self.session.delete(
             '{}/repos/{}/labels/{}'.format(
                 self.GH_API_ENDPOINT, repository, name
             )
        )
        if response.status_code != 204:
            raise GitHubError(response)

    @staticmethod
    def webhook_verify_signature(data, signature, secret, encoding='utf-8'):
        h = hmac.new(secret.encode(encoding), data, hashlib.sha1)
        return hmac.compare_digest('sha1=' + h.hexdigest(), signature)

###############################################################################
# Printing and logging
###############################################################################


class BasePrinter:
    SUCCESS_SUMMARY = '{} repo(s) updated successfully'
    ERROR_SUMMARY = '{} error(s) in total, please check log above'

    EVENT_CREATE = 'ADD'
    EVENT_DELETE = 'DEL'
    EVENT_UPDATE = 'UPD'
    EVENT_LABELS = 'LBL'

    RESULT_SUCCESS = 'SUC'
    RESULT_ERROR = 'ERR'
    RESULT_DRY = 'DRY'

    def __init__(self):
        self.repos = set()
        self.errors = 0

    def add_repo(self, slug):
        self.repos.add(slug)

    def event(self, event, result, repo, *args):
        if result == self.RESULT_ERROR:
            self.errors += 1

    def summary(self):
        pass

    def _create_summary(self):
        if self.errors > 0:
            return self.ERROR_SUMMARY.format(self.errors)
        return self.SUCCESS_SUMMARY.format(len(self.repos))


class Printer(BasePrinter):

    def event(self, event, result, repo, *args):
        super().event(event, result, repo, *args)
        if result == self.RESULT_ERROR:
            line_parts = ['ERROR: ' + event, repo, *args]
            click.echo('; '.join(line_parts))

    def summary(self):
        click.echo('SUMMARY: ' + self._create_summary())


class QuietPrinter(BasePrinter):
    pass


class VerbosePrinter(BasePrinter):

    LINE_START = '[{}][{}] {}'

    def event(self, event, result, repo, *args):
        super().event(event, result, repo, *args)
        line_parts = [self.LINE_START.format(event, result, repo), *args]
        click.echo('; '.join(line_parts))

    def summary(self):
        click.echo('[SUMMARY] ' + self._create_summary())

###############################################################################
# Processing changes (RUN and MODES)
###############################################################################


class RunModes:

    @staticmethod
    def _make_labels_dict(labels_spec):
        return {k.lower(): (k, v) for k, v in labels_spec.items()}

    @classmethod
    def update_mode(cls, labels, labels_specs):
        create = dict()
        update = dict()
        xlabels = cls._make_labels_dict(labels)
        for name, color in labels_specs.items():
            if name.lower() not in xlabels:
                create[name] = (name, color)
            elif name not in labels:  # changed case of name
                old_name = xlabels[name.lower()][0]
                update[old_name] = (name, color)
            elif labels[name] != color:
                update[name] = (name, color)
        return create, update, dict()

    @classmethod
    def replace_mode(cls, labels, labels_specs):
        create, update, delete = cls.update_mode(labels, labels_specs)
        delete = {n: (n, c) for n, c in labels.items()
                  if n not in labels_specs}
        return create, update, delete


class RunProcessor:

    MODES = {
        'update': RunModes.update_mode,
        'replace': RunModes.replace_mode
    }

    def __init__(self, github, printer=None):
        self.github = github
        self.printer = printer or QuietPrinter()

    def _process_generic(self, slug, key, data, event, method):
        old_name, name, color = key, data[0], data[1]
        try:
            method(slug, name=name, color=color, old_name=old_name)
        except GitHubError as error:
            self.printer.event(event, Printer.RESULT_ERROR,
                               slug, name, color, error.code_message)
        else:
            self.printer.event(event, Printer.RESULT_SUCCESS,
                               slug, name, color)

    def _process_create(self, slug, key, data):
        self._process_generic(slug, key, data, Printer.EVENT_CREATE,
                              self.github.create_label)

    def _process_update(self, slug, key, data):
        self._process_generic(slug, key, data, Printer.EVENT_UPDATE,
                              self.github.update_label)

    def _process_delete(self, slug, key, data):
        self._process_generic(slug, key, data, Printer.EVENT_DELETE,
                              self.github.delete_label)

    @staticmethod
    def _process(slug, changes, processor):
        for key, data in changes.items():
            processor(slug, key, data)

    def _run_one(self, slug, labels_specs, mode):
        self.printer.add_repo(slug)
        try:
            labels = self.github.list_labels(slug)
        except GitHubError as error:
            self.printer.event(Printer.EVENT_LABELS, Printer.RESULT_ERROR,
                               slug, error.code_message)
        else:
            create, update, delete = mode(labels, labels_specs)
            self._process(slug, create, self._process_create)
            self._process(slug, update, self._process_update)
            self._process(slug, delete, self._process_delete)

    def run(self, slugs, labels_specs, mode):
        for slug in slugs:
            self._run_one(slug, labels_specs, mode)
        self.printer.summary()
        return (DEFAULT_ERROR_RETURN if self.printer.errors > 0
                else DEFAULT_SUCCESS_RETURN)


class DryRunProcessor(RunProcessor):

    def __init__(self, github, printer=None):
        super().__init__(github, printer)

    def _process_create(self, slug, key, data):
        self.printer.event(Printer.EVENT_CREATE, Printer.RESULT_DRY,
                           slug, data[0], data[1])

    def _process_update(self, slug, key, data):
        self.printer.event(Printer.EVENT_UPDATE, Printer.RESULT_DRY,
                           slug, data[0], data[1])

    def _process_delete(self, slug, key, data):
        self.printer.event(Printer.EVENT_DELETE, Printer.RESULT_DRY,
                           slug, data[0], data[1])

###############################################################################
# Simple helpers
###############################################################################


DEFAULT_CONFIG_FILE = './config.cfg'


def create_config(config_filename=None, token=None):
    cfg = configparser.ConfigParser()
    cfg.optionxform = str
    cfg_filename = config_filename or DEFAULT_CONFIG_FILE

    if os.access(cfg_filename, os.R_OK):
        with open(cfg_filename) as f:
            cfg.read_file(f)
    if token is not None:
        cfg.read_dict({'github': {'token': token}})
    return cfg


def extract_labels(gh, template_opt, cfg):
    if template_opt is not None:
        return gh.list_labels(template_opt)
    if cfg.has_section('others') and 'template-repo' in cfg['others']:
        return gh.list_labels(cfg['others']['template-repo'])
    if cfg.has_section('labels'):
        return {name: str(color) for name, color in cfg['labels'].items()}
    click.echo('No labels specification has been found', err=True)
    sys.exit(NO_LABELS_SPEC_RETURN)


def extract_repos(cfg):
    if cfg.has_section('repos'):
        repos = cfg['repos'].keys()
        return [r for r in repos if cfg['repos'].getboolean(r, False)]
    click.echo('No repositories specification has been found', err=True)
    sys.exit(NO_REPOS_SPEC_RETURN)


def pick_printer(verbose, quiet):
    if verbose and not quiet:
        return VerbosePrinter
    if quiet and not verbose:
        return QuietPrinter
    return Printer


def pick_runner(dry_run):
    return DryRunProcessor if dry_run else RunProcessor


def gh_error_return(github_error):
    return GH_ERROR_RETURN.get(github_error.status_code, DEFAULT_ERROR_RETURN)


def retrieve_github_client(ctx):
    if 'GitHub' not in ctx.obj:
        click.echo('No GitHub token has been provided', err=True)
        sys.exit(NO_GH_TOKEN_RETURN)
    return ctx.obj['GitHub']

###############################################################################
# Flask task
###############################################################################


class LabelordChange:
    CHANGE_TIMEOUT = 10

    def __init__(self, action, name, color, new_name=None):
        self.action = action
        self.name = name
        self.color = None if action == 'deleted' else color
        self.old_name = new_name
        self.timestamp = int(time.time())

    @property
    def tuple(self):
        return self.action, self.name, self.color, self.old_name

    def __eq__(self, other):
        return self.tuple == other.tuple

    def is_valid(self):
        return self.timestamp > (int(time.time()) - self.CHANGE_TIMEOUT)


class LabelordWeb(flask.Flask):

    def __init__(self, labelord_config, github, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.labelord_config = labelord_config
        self.github = github
        self.ignores = {}

    def inject_session(self, session):
        self.github.set_session(session)

    def reload_config(self):
        config_filename = os.environ.get('LABELORD_CONFIG', None)
        self.labelord_config = create_config(
            token=os.getenv('GITHUB_TOKEN', None),
            config_filename=config_filename
        )
        self._check_config()
        self.github.token = self.labelord_config.get('github', 'token')

    @property
    def repos(self):
        return extract_repos(flask.current_app.labelord_config)

    def _check_config(self):
        if not self.labelord_config.has_option('github', 'token'):
            click.echo('No GitHub token has been provided', err=True)
            sys.exit(NO_GH_TOKEN_RETURN)
        if not self.labelord_config.has_section('repos'):
            click.echo('No repositories specification has been found',
                       err=True)
            sys.exit(NO_REPOS_SPEC_RETURN)
        if not self.labelord_config.has_option('github', 'webhook_secret'):
            click.echo('No webhook secret has been provided', err=True)
            sys.exit(NO_WEBHOOK_SECRET_RETURN)

    def _init_error_handlers(self):
        from werkzeug.exceptions import default_exceptions
        for code in default_exceptions:
            self.errorhandler(code)(LabelordWeb._error_page)

    def finish_setup(self):
        self._check_config()
        self._init_error_handlers()

    @staticmethod
    def create_app(config=None, github=None):
        cfg = config or create_config(
            token=os.getenv('GITHUB_TOKEN', None),
            config_filename=os.getenv('LABELORD_CONFIG', None)
        )
        gh = github or GitHub('')  # dummy, but will be checked later
        gh.token = cfg.get('github', 'token', fallback='')
        return LabelordWeb(cfg, gh, import_name=__name__)

    @staticmethod
    def _error_page(error):
        return flask.render_template('error.html', error=error), error.code

    def cleanup_ignores(self):
        for repo in self.ignores:
            self.ignores[repo] = [c for c in self.ignores[repo]
                                  if c.is_valid()]

    def process_label_webhook_create(self, label, repo):
        self.github.create_label(repo, label['name'], label['color'])

    def process_label_webhook_delete(self, label, repo):
        self.github.delete_label(repo, label['name'])

    def process_label_webhook_edit(self, label, repo, changes):
        name = old_name = label['name']
        color = label['color']
        if 'name' in changes:
            old_name = changes['name']['from']
        self.github.update_label(repo, name, color, old_name)

    def process_label_webhook(self, data):
        self.cleanup_ignores()
        action = data['action']
        label = data['label']
        repo = data['repository']['full_name']
        flask.current_app.logger.info(
            'Processing LABEL webhook event with action {} from {} '
            'with label {}'.format(action, repo, label)
        )
        if repo not in self.repos:
            return  # This repo is not being allowed in this app

        change = LabelordChange(action, label['name'], label['color'])
        if action == 'edited' and 'name' in data['changes']:
            change.new_name = label['name']
            change.name = data['changes']['name']['from']

        if repo in self.ignores and change in self.ignores[repo]:
            self.ignores[repo].remove(change)
            return  # This change was initiated by this service
        for r in self.repos:
            if r == repo:
                continue
            if r not in self.ignores:
                self.ignores[r] = []
            self.ignores[r].append(change)
            try:
                if action == 'created':
                    self.process_label_webhook_create(label, r)
                elif action == 'deleted':
                    self.process_label_webhook_delete(label, r)
                elif action == 'edited':
                    self.process_label_webhook_edit(label, r, data['changes'])
            except GitHubError:
                pass  # Ignore GitHub errors


app = LabelordWeb.create_app()


@app.before_first_request
def finalize_setup():
    flask.current_app.finish_setup()


@app.route('/', methods=['GET'])
def index():
    repos = flask.current_app.repos
    return flask.render_template('index.html', repos=repos)


@app.route('/', methods=['POST'])
def hook_accept():
    headers = flask.request.headers
    signature = headers.get('X-Hub-Signature', '')
    event = headers.get('X-GitHub-Event', '')
    data = flask.request.get_json()

    if not flask.current_app.github.webhook_verify_signature(
            flask.request.data, signature,
            flask.current_app.labelord_config.get('github', 'webhook_secret')
    ):
        flask.abort(401)

    if event == 'label':
        if data['repository']['full_name'] not in flask.current_app.repos:
            flask.abort(400, 'Repository is not allowed in application')
        flask.current_app.process_label_webhook(data)
        return ''
    if event == 'ping':
        flask.current_app.logger.info('Accepting PING webhook event')
        return ''
    flask.abort(400, 'Event not supported')


###############################################################################
# Click commands
###############################################################################


@click.group(name='labelord')
@click.option('--config', '-c', type=click.Path(exists=True),
              help='Path of the auth config file.')
@click.option('--token', '-t', envvar='GITHUB_TOKEN',
              help='GitHub API token.')
@click.version_option(version='0.2',
                      prog_name='labelord')
@click.pass_context
def cli(ctx, config, token):
    ctx.obj['config'] = create_config(config, token)
    ctx.obj['config'].optionxform = str
    if token is not None:
        ctx.obj['config'].read_dict({'github': {'token': token}})
    if ctx.obj['config'].has_option('github', 'token'):
        session = ctx.obj.get('session', requests.Session())
        ctx.obj['GitHub'] = GitHub(
            ctx.obj['config'].get('github', 'token'),
            session
        )


@cli.command(help='Listing accessible repositories.')
@click.pass_context
def list_repos(ctx):
    github = retrieve_github_client(ctx)
    try:
        repos = github.list_repositories()
        click.echo('\n'.join(repos))
    except GitHubError as error:
        click.echo(error, err=True)
        sys.exit(gh_error_return(error))


@cli.command(help='Listing labels of desired repository.')
@click.argument('repository')
@click.pass_context
def list_labels(ctx, repository):
    github = retrieve_github_client(ctx)
    try:
        labels = github.list_labels(repository)
        for name, color in labels.items():
            click.echo('#{} {}'.format(color, name))
    except GitHubError as error:
        click.echo(error, err=True)
        sys.exit(gh_error_return(error))


@cli.command(help='Run labels processing.')
@click.argument('mode', default='update', metavar='<update|replace>',
                type=click.Choice(['update', 'replace']))
@click.option('--template-repo', '-r', type=click.STRING,
              help='Repository which serves as labels template.')
@click.option('--dry-run', '-d', is_flag=True,
              help='Proceed with just dry run.')
@click.option('--verbose', '-v', is_flag=True,
              help='Really exhaustive output.')
@click.option('--quiet', '-q', is_flag=True,
              help='No output at all.')
@click.option('--all-repos', '-a', is_flag=True,
              help='Run for all repositories available.')
@click.pass_context
def run(ctx, mode, template_repo, dry_run, verbose, quiet, all_repos):
    github = retrieve_github_client(ctx)
    labels = extract_labels(
        github, template_repo,
        ctx.obj['config']
    )
    if all_repos:
        repos = github.list_repositories()
    else:
        repos = extract_repos(ctx.obj['config'])
    printer = pick_printer(verbose, quiet)()
    processor = pick_runner(dry_run)(github, printer)
    try:
        return_code = processor.run(repos, labels, processor.MODES[mode])
        sys.exit(return_code)
    except GitHubError as error:
        click.echo(error, err=True)
        sys.exit(gh_error_return(error))


@cli.command(help='Run master-to-master replication server.')
@click.option('--host', '-h', default='127.0.0.1',
              help='The interface to bind to.')
@click.option('--port', '-p', default=5000,
              help='The port to bind to.')
@click.option('--debug', '-d', is_flag=True,
              help='Turns on DEBUG mode.')
@click.pass_context
def run_server(ctx, host, port, debug):
    app.labelord_config = ctx.obj['config']
    app.github = retrieve_github_client(ctx)
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    cli(obj={})
