import argparse
import glob
import json
import logging
import os
import platform
import re
import subprocess
import sys


import github
import requests
import uritemplate

from lbrynet.core import log_support


def main(args=None):
    current_tag = None
    try:
        current_tag = subprocess.check_output(
            ['git', 'describe', '--exact-match', 'HEAD']).strip()
    except subprocess.CalledProcessError:
        log.info('Stopping as we are not currently on a tag')
        return

    if 'GH_TOKEN' not in os.environ:
        print 'Must set GH_TOKEN in order to publish assets to a release'
        return

    gh_token = os.environ['GH_TOKEN']
    auth = github.Github(gh_token)
    app_repo = auth.get_repo('lbryio/lbry-app')
    # TODO: switch lbryio/lbrynet-daemon to lbryio/lbry
    daemon_repo = auth.get_repo('lbryio/lbrynet-daemon')

    if not check_repo_has_tag(app_repo, current_tag):
        log.info('Tag %s is not in repo %s', current_tag, app_repo)
        # TODO: maybe this should be an error
        return

    app = get_app_artifact()
    release = get_release(app_repo, current_tag)
    upload_asset(release, app, gh_token)

    daemon = get_daemon_artifact()
    release = get_release(daemon_repo, current_tag)
    upload_asset(release, daemon, gh_token)


def check_repo_has_tag(repo, target_tag):
    tags = repo.get_tags().get_page(0)
    for tag in tags:
        if tag.name == target_tag:
            return True
    return False


def get_release(current_repo, current_tag):
    for release in current_repo.get_releases():
        if release.tag_name == current_tag:
            return release
    raise Exception('No release for {} was found'.format(current_tag))


def get_app_artifact():
    system = platform.system()
    if system == 'Darwin':
        return glob.glob('dist/mac/LBRY*.dmg')[0]
    elif system == 'Linux':
        return glob.glob('dist/LBRY*.deb')[0]
    elif system == 'Windows':
        return glob.glob('dist/LBRY*.exe')[0]
    else:
        raise Exception("I don't know about any artifact on {}".format(system))


def get_daemon_artifact():
    return glob.glob('dist/*.zip')[0]


def upload_asset(release, asset_to_upload, token):
    basename = os.path.basename(asset_to_upload)
    if is_asset_already_uploaded(release, basename):
        return
    print 'Release upload url:', release.upload_url
    upload_uri = uritemplate.expand(
        release.upload_url, {'name': basename})
    # using requests.post fails miserably with SSL EPIPE errors. I spent
    # half a day trying to debug before deciding to switch to curl.
    #
    # TODO: actually set the content type
    cmd = [
        'curl', '-sS', '-X', 'POST', '-u', ':{}'.format(os.environ['GH_TOKEN']),
        '--header', 'Content-Type:application/octet-stream',
        '--data-binary', '@{}'.format(asset_to_upload), upload_uri
    ]
    print 'Calling curl:'
    print cmd
    print
    p = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    print 'curl return code:', p.returncode
    if stderr:
        print 'stderr output from curl:'
        print stderr
    output = json.loads(stdout)
    print 'stdout from curl:'
    print stdout
    if 'errors' in output:
        raise Exception(output)
    else:
        log.info('Successfully uploaded to %s', output['browser_download_url'])


def is_asset_already_uploaded(release, basename):
    for asset in release.raw_data['assets']:
        if asset['name'] == basename:
            log.info('File %s has already been uploaded to %s', basename, release.tag_name)
            return True
    return False


if __name__ == '__main__':
    log = logging.getLogger('release-on-tag')
    log_support.configure_console(level='INFO')
    sys.exit(main())
else:
    log = logging.getLogger(__name__)
