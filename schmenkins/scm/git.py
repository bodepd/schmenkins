import os.path
import re

from schmenkins.utils import run_cmd

def poll(schmenkins, job, info):
    url = info['url']
    ref = 'refs/heads/%s' % (info.get('branch', 'master'),)

    cmd = ['git', 'ls-remote', info['url']]
    output = run_cmd(cmd)

    for l in output.split('\n'):
        if not l:
            continue

        parts = re.split('\s', l)
        if parts[1] == ref:
            job.build_revision = parts[0]
            break

    if job.build_revision is None:
        log.error('Did not find revision for %s for job' % (ref, job.name))
        return

    if not job.state.last_seen_revision:
        job.should_run = True
    elif job.state.last_seen_revision != job.build_revision:
        job.should_run = True

def checkout(schmenkins, job, info, revision):
    remote_name = 'origin' # I believe this can be overriden somehow

    if not os.path.isdir(os.path.join(job.workspace(), '.git')):
        run_cmd(['git', 'init'], cwd=job.workspace(), dry_run=schmenkins.dry_run)
        run_cmd(['git', 'remote', 'add', remote_name, info['url']],
                cwd=job.workspace(), dry_run=schmenkins.dry_run)

    run_cmd(['git', 'remote', 'set-url', remote_name, info['url']],
             cwd=job.workspace(), dry_run=schmenkins.dry_run)

    run_cmd(['git', 'fetch', remote_name],
             cwd=job.workspace(), dry_run=schmenkins.dry_run)

    rev = job.build_revision or '%s/%s' % (remote_name, info.get('branch', 'master'))
    run_cmd(['git', 'reset', '--hard', rev], cwd=job.workspace(), dry_run=schmenkins.dry_run)
