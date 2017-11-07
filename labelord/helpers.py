import configparser
import os
import sys
import click

from labelord.consts import DEFAULT_CONFIG_FILE, NO_LABELS_SPEC_RETURN, \
    NO_REPOS_SPEC_RETURN


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
