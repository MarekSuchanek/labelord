import click
import flask
import os
import sys
import time

from labelord.github import GitHub, GitHubError
from labelord.consts import NO_GH_TOKEN_RETURN, \
    NO_REPOS_SPEC_RETURN, NO_WEBHOOK_SECRET_RETURN
from labelord.helpers import create_config, extract_repos


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
