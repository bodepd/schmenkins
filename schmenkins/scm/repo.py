import logging
import os.path
import re
import shutil
from xml.etree import ElementTree

from schmenkins.utils import run_cmd

LOG = logging.getLogger(__name__)

def poll(schmenkins, job, info):
    # Checkout (we don't know any other way to find all this info)
    checkout(schmenkins, job, info)

    cmd = ['repo', 'manifest', '-o', '-', '-r']
    output = run_cmd(cmd, cwd=job.workspace(), dry_run=schmenkins.dry_run)

    tree = ElementTree.fromstring(output)

    project_revisions = {project.attrib['name']: project.attrib['revision']
                         for project in tree.findall('project')}

    cmd = ['git', 'rev-parse', 'HEAD']
    output = run_cmd(cmd, cwd=os.path.join(job.workspace(), '.repo', 'manifests'),
                     dry_run=schmenkins.dry_run)
    manifest_revision = output.strip()

    project_revisions['_manifest'] = manifest_revision

    job.build_revision = project_revisions

    if not job.state.last_seen_revision:
        job.should_run = True
    elif job.state.last_seen_revision != job.build_revision:
        job.should_run = True

def checkout(schmenkins, job, info, build=None):
    logger = build and build.logger or LOG
    cmd = ['repo', 'init', '-u', info['manifest-url']]

    if 'manifest-file' in info:
        cmd += ['-m', info['manifest-file']]

    if 'manifest-branch' in info:
        cmd += ['-b', info['manifest-branch']]

    run_cmd(cmd, cwd=job.workspace(), logger=logger, dry_run=schmenkins.dry_run)

    cmd = ['repo', 'sync', '-d', '-c', '-q']
    run_cmd(cmd, cwd=job.workspace(), logger=logger, dry_run=schmenkins.dry_run)
