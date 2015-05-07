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
import os.path
import re
import subprocess
import sys
import time
from croniter import croniter
from pprint import pprint
from jenkins_jobs.builder import Builder

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
    
def run_cmd(args):
    proc = subprocess.Popen(args, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    return stdout
    
def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser()

    parser.add_argument('basedir', help="Base directory")
    parser.add_argument('config', help="Config file")

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

    base = datetime.datetime.fromtimestamp(state.last_run or 0)
    now = datetime.datetime.now()

    state.last_seen_revisions = state.last_seen_revisions or {}

    for job in builder.parser.jobs:
        job_dir = os.path.join(args.basedir, 'jobs', job['name'])
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
                    print job['name'], 'due for a run'
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

                   if job['name'] not in state.last_seen_revisions:
                       run = True

        if run:
            print 'Running builders for', job['name'], 'rev:', rev
            state.last_seen_revisions[job['name']] = ref

        
    state.last_run = time.mktime(now.timetuple())
    state.save(statefile)

if __name__ == '__main__':
    sys.exit(not main())

