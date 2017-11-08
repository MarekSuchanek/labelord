import click
import requests
import sys

from labelord.web import app
from labelord.consts import NO_GH_TOKEN_RETURN, GH_ERROR_RETURN, \
    DEFAULT_ERROR_RETURN
from labelord.github import GitHub, GitHubError
from labelord.printing import VerbosePrinter, QuietPrinter, Printer
from labelord.run_logic import DryRunProcessor, RunProcessor
from labelord.helpers import create_config, extract_repos, extract_labels


def gh_error_return(github_error):
    return GH_ERROR_RETURN.get(github_error.status_code, DEFAULT_ERROR_RETURN)


def retrieve_github_client(ctx):
    if 'GitHub' not in ctx.obj:
        click.echo('No GitHub token has been provided', err=True)
        sys.exit(NO_GH_TOKEN_RETURN)
    return ctx.obj['GitHub']


def pick_printer(verbose, quiet):
    if verbose and not quiet:
        return VerbosePrinter
    if quiet and not verbose:
        return QuietPrinter
    return Printer


def pick_runner(dry_run):
    return DryRunProcessor if dry_run else RunProcessor


@click.group(name='labelord')
@click.option('--config', '-c', type=click.Path(exists=True),
              help='Path of the auth config file.')
@click.option('--token', '-t', envvar='GITHUB_TOKEN',
              help='GitHub API token.')  # prompt would be better,
@click.version_option(version='0.3',
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


def main():
    cli(obj={})
