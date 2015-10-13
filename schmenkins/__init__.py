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
import formic
import importlib
import json
import logging
import os
import os.path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from glob import glob
from fnmatch import fnmatch
from pprint import pprint
from jenkins_jobs.builder import Builder
from schmenkins.state import State
from schmenkins.utils import run_cmd, ensure_dir, ensure_dir_wrapper

LOG = logging.getLogger(__name__)

BUILD_STATES = ['SUCCESS',
                'FAILED',
                'ABORTED',
                'RUNNING',
                'SCHEDULED']

class SchmenkinsSummary(State):
    attrs = ['all_builds']

class SchmenkinsState(State):
    attrs = ['last_run',
             'jobs']

class JobState(State):
    attrs = ['last_seen_revision',
             'last_succesful_build',
             'last_failed_build',
             'next_build_number',
             'last_build',
             'running',
             'state',
             'triggers_completed_time']

class BuildState(State):
    attrs = ['state',
             'start_time',
             'end_time',
             'commit_info',
             'commit_info_url',
             'id']

class SchmenkinsBuild(object):
    def __init__(self, job, build_revision=None, parameters=None, build_number=None):
        if parameters is None:
            parameters = {}
        self._parameters = parameters
        self.job = job
        self.build_revision = build_revision
        self.build_number = build_number
        self.state = BuildState()

        if self.build_number:
            self.state.path = self.state_file()

        self.logger = None

    def __str__(self):
        return 'Build %s of %s' % (self.build_number, self.job)

    def state_file(self):
        return os.path.join(self.build_dir(), 'state.json')

    def get_next_build_number(self):
        self.build_number = self.job.state.next_build_number or 1
        self.job.state.next_build_number = self.build_number + 1

    def parameters(self):
        retval = self._parameters.copy()
        retval['BUILD_NUMBER'] = self.build_number
        retval['JOB_NAME'] = self.job.name
        return retval

    @ensure_dir_wrapper
    def build_dir(self):
        return os.path.join(self.job.build_records(), str(self.build_number))

    def log_file(self):
        return os.path.join(self.build_dir(), 'consoleLog.txt')

    @ensure_dir_wrapper
    def artifact_dir(self):
        return os.path.join(self.build_dir(), 'artifacts')

    def setup_logging(self):
        self.logger = logging.getLogger('%s-%d' % (self.job, self.build_number))
        self.logger.setLevel(logging.DEBUG)

        logfp = logging.FileHandler(self.log_file())
        logfp.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s: %(message)s')

        logfp.setFormatter(formatter)
        self.logger.addHandler(logfp)

    def run(self):
        self.get_next_build_number()
        LOG.info('Assigned build number %d to job %s' % (self.build_number,
                                                         self.job))
        self.state.id = self.build_number
        self.job.schmenkins.add_recent_build(self)

        # We're encoding in JSON. JS convention is microsends since the epoch
        self.state.start_time = time.time() * 1000
        self.state.path = self.state_file()
        self.state.state = 'RUNNING'

        self.setup_logging()
        try:
            self.job.checkout(self)
            self.job.build(self)
            self.state.state = 'SUCCESS'
        except exceptions.SchmenkinsCommandFailed, e:
            self.state.state = 'FAILED'

        self.state.end_time = time.time() * 1000
        self.job.publish(self)

        self.job.state.last_seen_revision = self.build_revision

        self.job.state.last_build = self.state
        if self.state.state == 'SUCCESS':
            self.job.state.last_succesful_build = self.state
        elif self.state.state == 'FAILED':
            self.job.state.last_failed_build = self.state


class SchmenkinsJob(object):
    def __init__(self, schmenkins, job_dict):
        self.schmenkins = schmenkins
        self._job_dict = job_dict

        self.state = JobState(path=self.state_file())

        self.type = self._job_dict.get('project-type', 'freestyle')

        if self.type != 'freestyle':
            raise exceptions.UnsupportedConfig('Unsupported job type:', self.type)

        self.should_poll = False
        self.should_run = False
        self.build_revision = None

    def __str__(self):
        return self.name

    @property
    def name(self):
        return self._job_dict['name']

    @ensure_dir_wrapper
    def job_dir(self):
        return os.path.join(self.schmenkins.jobs_dir(), self.name)

    def state_file(self):
        return os.path.join(self.job_dir(), 'state.json')

    @ensure_dir_wrapper
    def workspace(self):
        return os.path.join(self.job_dir(), 'workspace')

    @ensure_dir_wrapper
    def build_records(self):
        return os.path.join(self.job_dir(), 'build_records')

    def process_triggers(self):
        events = []
        for trigger in self._job_dict.get('triggers', []):
            plugin_name = trigger.keys()[0]
            try:
                plugin = importlib.import_module('schmenkins.triggers.%s' % (plugin_name,))
            except ImportError:
                raise exceptions.UnsupportedConfig('Trigger Plugin: %s' % (plugin_name,))
            events += plugin.run(self.schmenkins, self, trigger[plugin_name])
        return events


    def poll(self):
        for scm in self._job_dict.get('scm', []):
            plugin_name = scm.keys()[0]
            try:
                plugin = importlib.import_module('schmenkins.scm.%s' % (plugin_name,))
            except ImportError:
                raise exceptions.UnsupportedConfig('SCM Plugin: %s' % (plugin_name,))
            plugin.poll(self.schmenkins, self, scm[plugin_name])

    def run(self, parameters=None):
        params = {} if parameters is None else parameters
        build = SchmenkinsBuild(self, self.build_revision, params)

        self.state.running = build.state
        build.run()
        self.state.running = None

        return build

    def checkout(self, revision):
        for scm in self._job_dict.get('scm', []):
            plugin_name = scm.keys()[0]
            try:
                plugin = importlib.import_module('schmenkins.scm.%s' % (plugin_name,))
            except ImportError:
                raise exceptions.UnsupportedConfig('SCM Plugin: %s' % (plugin_name,))
            plugin.checkout(self.schmenkins, self, scm[plugin_name], revision)

    def build(self, build):
        builders = self._job_dict.get('builders', [])
        for builder in builders:
            plugin_name = builder.keys()[0]
            try:
                plugin = importlib.import_module('schmenkins.builders.%s' % (plugin_name,))
            except ImportError:
                raise exceptions.UnsupportedConfig('Builder Plugin: %s' % (plugin_name,))
            plugin.run(self.schmenkins, self, builder[plugin_name], build)


    def publish(self, build):
        publishers = self._job_dict.get('publishers', [])
        for publisher in publishers:
            plugin_name = publisher.keys()[0]
            try:
                plugin = importlib.import_module('schmenkins.publishers.%s' % (plugin_name,))
            except ImportError:
                raise exceptions.UnsupportedConfig('Publisher Plugin: %s' % (plugin_name,))
            plugin.publish(self.schmenkins, self, publisher[plugin_name], build)


class Schmenkins(object):
    def __init__(self, basedir, cfgfile, ignore_timestamp=False, dry_run=False):
        self.basedir = basedir
        self.cfgfile = cfgfile
        self.ignore_timestamp = ignore_timestamp
        self.dry_run = dry_run
        self.state = SchmenkinsState(path=self.state_file())
        self.summary = SchmenkinsSummary(path=self.summary_file())
        self.builder = self.get_builder()
        self.builder.load_files(self.cfgfile)
        self.builder.parser.expandYaml(None)

        if not hasattr(self.state, 'jobs') or self.state.jobs is None:
            self.state.jobs = {}

        self.jobs = {job['name']: job for job in self.builder.parser.jobs}
        self._jobs = {}

        if ignore_timestamp or self.state.last_run is None:
            self.last_run = 0
        else:
            self.last_run = self.state.last_run

        self.base_timestamp = datetime.datetime.fromtimestamp(self.last_run)
        self.now = datetime.datetime.now()

    def install_ui(self):
        uidir = os.path.join(os.path.dirname(__file__), 'www')
        self._sync_tree(uidir, self.basedir)

    def _sync_tree(self, src, dst):
        names = os.listdir(src)
        if not os.path.isdir(dst):
            os.makedirs(dst)
        for name in names:
            srcname = os.path.join(src, name)
            dstname = os.path.join(dst, name)

            if os.path.isdir(srcname):
                self._sync_tree(srcname, dstname)
            else:
                shutil.copy2(srcname, dstname)

    def add_recent_build(self, build):
        if not self.summary.all_builds:
            self.summary.all_builds = {}

        if not build.job.name in self.summary.all_builds:
            self.summary.all_builds[build.job.name] = {}

        self.summary.all_builds[build.job.name][build.build_number] = build.state

        fpath = os.path.join(self.basedir, 'recent_builds.json')
        try:
            with open(fpath, 'r') as fp:
                data = json.load(fp)
        except IOError:
            data = []
        data.insert(0, {'job': build.job.name, 'id': build.build_number})
        with open(fpath, 'w') as fp:
            json.dump(data, fp)

    def get_builder(self):
        return Builder('fakeurl',
                       'fakeuser',
                       'fakepassword',
                       plugins_list=[])

    def state_file(self):
        ensure_dir(self.basedir)
        return os.path.join(self.basedir, 'state.json')

    def summary_file(self):
        ensure_dir(self.basedir)
        return os.path.join(self.basedir, 'summary.json')

    def jobs_dir(self):
        return os.path.join(self.basedir, 'jobs')

    def get_job(self, job_name):
        if job_name not in self._jobs:
            self._jobs[job_name] = SchmenkinsJob(self, self.jobs[job_name])
        return self._jobs[job_name]

    # this is the code that does all of the processing.
    def handle_job(self, job_name, force_build=False):
        job = self.get_job(job_name)
        self.state.jobs[job.name] = job.state
        events = None

        logging.info('Processing triggers for %s' % (job,))
        # see if the triggers result in any created events
        if not force_build:
            # keep track of the events that might need to become builds
            # NOTE: this has side effects and modifies the state of the job
            # object
            events = job.process_triggers()

        logging.info('should_poll: %r, should_run: %r, force_build: %r' %
                     (job.should_poll, job.should_run, force_build))
        # poll if we got a trigger that we should poll
        if job.should_poll and not job.should_run and not force_build:
            job.poll()

        logging.info('should_run: %r, force_build: %r' %
                     (job.should_run, force_build))
        if force_build or job.should_run or events is not None:
            if events is None or all(v is None for v in events):
                build = job.run()
            else:
                for event in events:
                  if event.get('mergeable', True):
                      build = job.run(event['build_params'])
                  else:
                      print "Found an unmergable build"
                  job.state.triggers_completed_time = event['time']


def generate_summary(basedir):
    data = {'all_builds': {}}
    try:
        for job_name in os.listdir(os.path.join(basedir, 'jobs')):
            data['all_builds'][job_name] = {}
            try:
                for build in os.listdir(os.path.join(basedir, 'jobs', job_name, 'build_records')):
                    data['all_builds'][job_name][build] = json.load(open(os.path.join(basedir, 'jobs', job_name, 'build_records', build, 'state.json'), 'r'))
            except OSError:
                pass
    except OSError:
        pass

    ensure_dir(basedir)
    json.dump(data, open(os.path.join(basedir, 'summary.json'), 'w'))


def migrate(basedir):
    if not os.path.exists(os.path.join(basedir, 'summary.json')):
        generate_summary(basedir)


def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser()

    parser.add_argument('--dry-run', action='store_true', default=False,
                        help="Don't actually do anything")
    parser.add_argument('--ignore-timestamp', action='store_true', default=False,
                        help="Ignore last timestamp")
    parser.add_argument('--force-build', action='store_true', default=False,
                        help="Always build specified jobs")
    parser.add_argument('basedir', help="Base directory")
    parser.add_argument('config', help="Config file")
    parser.add_argument('jobs', nargs='*', help="Only process this/these job(s)")

    args = parser.parse_args()

    migrate(args.basedir)

    schmenkins = Schmenkins(args.basedir, args.config, args.ignore_timestamp, args.dry_run)

    schmenkins.install_ui()

    for job in schmenkins.jobs:
        if args.jobs and not any([fnmatch(job, job_glob) for job_glob in args.jobs]):
            logging.info('Skipping job: %s' % (job,))
            continue

        logging.info('Handling job: %s' % (job,))
        schmenkins.handle_job(job, force_build=args.force_build)

    schmenkins.state.last_run = time.mktime(schmenkins.now.timetuple())

if __name__ == '__main__':
    sys.exit(not main())

