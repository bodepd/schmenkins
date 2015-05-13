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
             'state']

class BuildState(State):
    attrs = ['state',
             'start_time',
             'end_time',
             'revision',
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
        logging.info('Assigned build number %d to job %s' % (self.build_number,
                                                             self.job))
        self.state.id = self.build_number

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
        for trigger in self._job_dict.get('triggers', []):
            plugin_name = trigger.keys()[0]
            try:
                plugin = importlib.import_module('schmenkins.triggers.%s' % (plugin_name,))
            except ImportError:
                raise exceptions.UnsupportedConfig('Trigger Plugin: %s' % (plugin_name,))
            plugin.run(self.schmenkins, self, trigger[plugin_name])


    def poll(self):
        for scm in self._job_dict.get('scm', []):
            plugin_name = scm.keys()[0]
            try:
                plugin = importlib.import_module('schmenkins.scm.%s' % (plugin_name,))
            except ImportError:
                raise exceptions.UnsupportedConfig('SCM Plugin: %s' % (plugin_name,))
            plugin.poll(self.schmenkins, self, scm[plugin_name])

    def run(self, parameters=None):
        build = SchmenkinsBuild(self, self.build_revision, parameters)

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
            plugin.checkout(self.schmenkins, self, scm[plugin_name])

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
        self.builder = self.get_builder()
        self.builder.load_files(self.cfgfile)
        self.builder.parser.expandYaml(None)

        if not hasattr(self.state, 'jobs') or self.state.jobs is None:
            self.state.jobs = {}

        self.jobs = {job['name']: job for job in self.builder.parser.jobs}

        if ignore_timestamp or self.state.last_run is None:
            self.last_run = 0
        else:
            self.last_run = self.state.last_run

        self.base_timestamp = datetime.datetime.fromtimestamp(self.last_run)
        self.now = datetime.datetime.now()

    def get_builder(self):
        return Builder('fakeurl',
                       'fakeuser',
                       'fakepassword',
                       plugins_list=[])

    def state_file(self):
        ensure_dir(self.basedir)
        return os.path.join(self.basedir, 'state.json')

    def jobs_dir(self):
        return os.path.join(self.basedir, 'jobs')

    def handle_job(self, job_dict, force_build=False):
        job = SchmenkinsJob(self, job_dict)
        self.state.jobs[job.name] = job.state

        logging.info('Processing triggers for %s' % (job,))
        if not force_build:
            job.process_triggers()

        logging.info('should_poll: %r, should_run: %r, force_build: %r' %
                     (job.should_poll, job.should_run, force_build))
        if job.should_poll and not job.should_run and not force_build:
            job.poll()

        logging.info('should_run: %r, force_build: %r' %
                     (job.should_run, force_build))
        if force_build or job.should_run:
            build = job.run()

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

    schmenkins = Schmenkins(args.basedir, args.config, args.ignore_timestamp, args.dry_run)

    for job in schmenkins.jobs:
        if args.jobs and not any([fnmatch(job, job_glob) for job_glob in args.jobs]):
            logging.info('Skipping job: %s' % (job,))
            continue

        logging.info('Handling job: %s' % (job,))
        schmenkins.handle_job(schmenkins.jobs[job], force_build=args.force_build)

    schmenkins.state.last_run = time.mktime(schmenkins.now.timetuple())

if __name__ == '__main__':
    sys.exit(not main())

