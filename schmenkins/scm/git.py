import logging
import os.path
import re
import shutil

from schmenkins.utils import run_cmd

LOG = logging.getLogger(__name__)

def poll(schmenkins, job, info):
    url = info['url']
    ref = 'refs/heads/%s' % (info.get('branch', 'master'),)

    cmd = ['git', 'ls-remote', info['url']]
    output = run_cmd(cmd, dry_run=schmenkins.dry_run)

    for l in output.split('\n'):
        if not l:
            continue

        parts = re.split('\s', l)
        if parts[1] == ref:
            job.build_revision = parts[0]
            break

    if job.build_revision is None:
        LOG.error('Did not find revision for %s for job %s' % (ref, job.name))
        return

    if not job.state.last_seen_revision:
        job.should_run = True
    elif job.state.last_seen_revision != job.build_revision:
        job.should_run = True

def checkout(schmenkins, job, info, build):
    remote_name = 'origin' # I believe this can be overriden somehow

    if info.get('wipe-workspace', True):
        shutil.rmtree(job.workspace())

    if not os.path.isdir(os.path.join(job.workspace(), '.git')):
        run_cmd(['git', 'init'],
                 cwd=job.workspace(),
                 logger=build.logger,
                 dry_run=schmenkins.dry_run)

        run_cmd(['git', 'remote', 'add', remote_name, info['url']],
                cwd=job.workspace(), logger=build.logger, dry_run=schmenkins.dry_run)

    run_cmd(['git', 'remote', 'set-url', remote_name, info['url']],
             cwd=job.workspace(),
             logger=build.logger,
             dry_run=schmenkins.dry_run)

    run_cmd(['git', 'fetch', remote_name],
             cwd=job.workspace(),
             logger=build.logger,
             dry_run=schmenkins.dry_run)

    rev = build.build_revision or '%s/%s' % (remote_name, info.get('branch', 'master'))
    run_cmd(['git', 'reset', '--hard', rev],
            cwd=job.workspace(), logger=build.logger, dry_run=schmenkins.dry_run)

    commit = run_cmd(['git', 'rev-parse', 'HEAD'],
                     cwd=job.workspace(), logger=build.logger, dry_run=schmenkins.dry_run).strip()

    build.state.commit_info = run_cmd(['git', 'log', '-1', '--oneline'],
                                      cwd=job.workspace(), logger=build.logger, dry_run=schmenkins.dry_run).strip()

    if job._job_dict.get('properties', {}).get('github', False):
        github_url = job._job_dict['properties']['github']
        build.state.commit_info_url = '%s/commit/%s' % (github_url, commit)

    build._parameters['GIT_COMMIT'] = commit
