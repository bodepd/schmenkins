#!/usr/bin/env python
#
#   Copyright 2015 Linux2Go
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
import argparse
import datetime
import json
import logging
import os.path
import re
import subprocess
import sys
import tempfile
import time
from croniter import croniter
from fnmatch import fnmatch
from pprint import pprint
from jenkins_jobs.builder import Builder


logging.basicConfig(level=logging.INFO)

class State(object):
    attrs = ['last_run', 'last_seen_revisions']

    def __init__(self, **kwargs):
        for attr in self.attrs:
            setattr(self, attr, kwargs.get(attr, None))

    def load(self, path):
        try:
            with open(path, 'r') as fp:
                data = json.load(fp)
        except IOError:
            data = {}
        for attr in self.attrs:
            if attr in data:
                setattr(self, attr, data[attr])

    def save(self, path):
        data = {}
        for attr in self.attrs:
            if hasattr(self, attr):
                data[attr] = getattr(self, attr)

        with open(path, 'w') as fp:
            json.dump(data, fp)

def run_cmd(args, cwd=None, dry_run=False):
    if dry_run:
        logging.info('Would have run command: %r' % (args,))
        return ''
    else:
        logging.info('Running command: %r' % (args,))
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, cwd=cwd)
        stdout, stderr = proc.communicate()
        logging.debug('Command returned: %r' % (stdout,))
        return stdout

def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser()

    parser.add_argument('--dry-run', action='store_true', default=False,
                        help="Don't actually do anything")
    parser.add_argument('--ignore-timestamp', action='store_true', default=False,
                        help="Ignore last timestamp")
    parser.add_argument('basedir', help="Base directory")
    parser.add_argument('config', help="Config file")
    parser.add_argument('jobs', nargs='*', help="Only process this/these job(s)")

    args = parser.parse_args()

    statefile = os.path.join(args.basedir, 'state.json')
    if not os.path.isdir(args.basedir):
        os.mkdir(args.basedir)

    state = State()

    state.load(statefile)

    builder = Builder('fakeurl',
                      'fakeuser',
                      'fakepassword',
                      plugins_list=[])

    builder.load_files(args.config)
    builder.parser.expandYaml(None)

    if args.ignore_timestamp or not state.last_run:
        last_run = 0
    else:
        last_run = state.last_run

    base = datetime.datetime.fromtimestamp(last_run)
    now = datetime.datetime.now()

    state.last_seen_revisions = state.last_seen_revisions or {}

    for job in builder.parser.jobs:
        if args.jobs and not any([fnmatch(job['name'], job_glob) for job_glob in args.jobs]):
            logging.info('Skipping job: %s' % (job['name'],))
            continue

        logging.info('Handling job: %s' % (job['name'],))

        job_dir = os.path.join(args.basedir, 'jobs', job['name'])

        if not os.path.exists(job_dir):
            os.makedirs(job_dir)

        workspace = os.path.join(job_dir, 'workspace')

        style = job.get('project-style', 'freestyle')

        if style != 'freestyle':
            print 'Unsupported job style:', style
            continue

        run = False
        poll = False

        for trigger in job.get('triggers', []):
            if 'pollscm' in trigger:
                # This sucks
                cron = trigger['pollscm'].replace('H/', '*/')
                next_poll = croniter(cron, base).get_next(datetime.datetime)
                if next_poll < now:
                    logging.debug('%s should have been polled %s. Polling now.' % (job['name'], next_poll))
                    poll = True

        if poll:
            for scm in job.get('scm', []):
               if 'git' in scm:
                   git = scm['git']
                   url = git['url']
                   ref = 'refs/heads/%s' % (git.get('branch', 'master'),)

                   cmd = ['git', 'ls-remote', git['url']]
                   output = run_cmd(cmd)

                   rev = None
                   for l in output.split('\n'):
                       if not l:
                           continue

                       parts = re.split('\s', l)
                       if parts[1] == ref:
                           rev = parts[0]
                           break

                   if rev is None:
                       log.error('Did not find revision for %s for job' % (ref, job['name']))
                       continue

                   if job['name'] not in state.last_seen_revisions:
                       run = True
                   elif state.last_seen_revisions[job['name']] != rev:
                       run = True

        if run:
            for scm in job.get('scm', []):
                if 'git' in scm:
                    git = scm['git']
                    remote_name = 'origin' # I believe this can be overriden somehow

                    if os.path.exists(workspace) and os.path.isdir(workspace):
                        run_cmd(['git', 'remote', 'set-url', 'origin', git['url']],
                                cwd=workspace, dry_run=args.dry_run)
                    else:
                        run_cmd(['git', 'clone', git['url'], workspace], dry_run=args.dry_run)

                    run_cmd(['git', 'reset', '--hard', rev], cwd=workspace, dry_run=args.dry_run)


            if not os.path.exists(workspace):
                os.mkdir(workspace)

            builders = job.get('builders', [])
            for builder in builders:
                for builder_type in builder:
                    if builder_type == 'shell':
                        with tempfile.NamedTemporaryFile(delete=False) as fp:
                            try:
                                os.chmod(fp.name, 0o0700)
                                fp.write(builder[builder_type])
                                fp.close()

                                run_cmd(fp.name, cwd=workspace, dry_run=args.dry_run)
                            finally:
                                os.unlink(fp.name)
                    else:
                        print builder_type, builder[builder_type]
            state.last_seen_revisions[job['name']] = rev


    state.last_run = time.mktime(now.timetuple())
    state.save(statefile)

if __name__ == '__main__':
    sys.exit(not main())

