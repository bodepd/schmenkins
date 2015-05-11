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
import json
import logging
import os.path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from croniter import croniter
from glob import glob
from fnmatch import fnmatch
from pprint import pprint
from jenkins_jobs.builder import Builder

logging.basicConfig(level=logging.INFO)

itpl_regex = re.compile('\$({)?([a-z_][a-z0-9_]*)(?(1)})', re.VERBOSE | re.IGNORECASE)

def itpl(s, params):
    return itpl_regex.sub(lambda m:str(params.get(m.group(2), '')), s)


class State(object):
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

class SchmenkinsState(State):
    attrs = ['last_run']

class JobState(State):
    attrs = ['last_seen_revision',
             'last_succesful_build',
             'last_failed_build',
             'next_build_number']

def run_cmd(args, cwd=None, dry_run=False, capture_stdout=False):
    if dry_run:
        logging.info('Would have run command: %r' % (args,))
        return ''
    else:
        logging.info('Running command: %r' % (args,))

        kwargs = {}
        if capture_stdout:
            kwargs['stdout'] = subprocess.PIPE

        proc = subprocess.Popen(args, cwd=cwd, **kwargs)
        stdout, stderr = proc.communicate()
        logging.debug('Command returned: %r' % (stdout,))

        if proc.returncode != 0:
            raise SchmenkinsCommandFailed('%r failed with return code %d.' % (args, proc.returncode))

        return stdout

def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)
    return path

def ensure_dir_wrapper(func):
    def wrapper(*args, **kwargs):
        return ensure_dir(func(*args, **kwargs))
    return wrapper

class UnsupportedConfig(Exception):
    pass

class SchmenkinsCommandFailed(Exception):
    pass

class SchmenkinsBuild(object):
    def __init__(self, job, build_revision=None, parameters=None, build_number=None):
        if parameters is None:
            parameters = {}
        self._parameters = parameters
        self.job = job
        self.build_revision = build_revision
        self.build_number = build_number
        self.state = None

    def __str__(self):
        return 'Build %s of %s' % (self.build_number, self.job)

    def get_next_build_number(self):
        self.build_number = self.job.state.next_build_number or 1
        self.job.state.next_build_number = self.build_number + 1
        self.job.save_state()

    def parameters(self):
        retval = self._parameters.copy()
        retval['BUILD_NUMBER'] = self.build_number
        retval['JOB_NAME'] = self.job.name
        return retval

    @ensure_dir_wrapper
    def build_dir(self):
        return os.path.join(self.job.build_records(), str(self.build_number))

    @ensure_dir_wrapper
    def artifact_dir(self):
        return os.path.join(self.build_dir(), 'artifacts')

    def run(self):
        self.get_next_build_number()
        try:
            self.job.checkout(self)
            self.job.build(self)
        except SchmenkinsCommandFailed, e:
            self.state = 'FAILED'

        self.job.publish(self)

        self.job.state.last_seen_revision = self.build_revision
        self.job.save_state()


class SchmenkinsJob(object):
    def __init__(self, schmenkins, job_dict):
        self.schmenkins = schmenkins
        self._job_dict = job_dict

        self.state = JobState()
        self.load_state()

        self.style = self._job_dict.get('project-style', 'freestyle')

        if self.style != 'freestyle':
            raise UnsupportedConfig('Unsupported job style:', style)

        self.should_poll = False
        self.should_run = False
        self.build_revision = None

    def __str__(self):
        return self.name


    @property
    def name(self):
        return self._job_dict['name']

    def load_state(self):
        self.state.load(self.state_file())

    def save_state(self):
        self.state.save(self.state_file())

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
            if 'pollscm' in trigger:
                # This sucks
                cron = trigger['pollscm'].replace('H/', '*/')
                next_poll = croniter(cron, self.schmenkins.base_timestamp).get_next(datetime.datetime)
                if next_poll < self.schmenkins.now:
                    logging.debug('%s should have been polled %s. Polling now.' % (self.name, next_poll))
                    self.should_poll = True

            if 'timed' in trigger:
                # This also sucks
                cron = trigger['timed'].replace('H/', '*/')
                next_poll = croniter(cron, self.schmenkins.base_timestamp).get_next(datetime.datetime)
                if next_poll < self.schmenkins.now:
                    logging.debug('%s should have run %s. Running now.' % (self.name, next_poll))
                    self.should_run = True

    def poll(self):
        for scm in self._job_dict.get('scm', []):
           if 'git' in scm:
               git = scm['git']
               url = git['url']
               ref = 'refs/heads/%s' % (git.get('branch', 'master'),)

               cmd = ['git', 'ls-remote', git['url']]
               output = run_cmd(cmd, capture_stdout=True)

               for l in output.split('\n'):
                   if not l:
                       continue

                   parts = re.split('\s', l)
                   if parts[1] == ref:
                       self.build_revision = parts[0]
                       break

               if self.build_revision is None:
                   log.error('Did not find revision for %s for job' % (ref, self.name))
                   continue

               if not self.state.last_seen_revision:
                   self.should_run = True
               elif self.state.last_seen_revision != self.build_revision:
                   self.should_run = True

    def run(self, parameters=None):
        build = SchmenkinsBuild(self, self.build_revision, parameters)
        build.run()

    def checkout(self, revision):
        for scm in self._job_dict.get('scm', []):
            if 'git' in scm:
                git = scm['git']
                remote_name = 'origin' # I believe this can be overriden somehow

                if not os.path.isdir(os.path.join(self.workspace(), '.git')):
                    run_cmd(['git', 'init'], cwd=self.workspace(), dry_run=self.schmenkins.dry_run)
                    run_cmd(['git', 'remote', 'add', remote_name, git['url']],
                            cwd=self.workspace(), dry_run=self.schmenkins.dry_run)

                run_cmd(['git', 'remote', 'set-url', remote_name, git['url']],
                         cwd=self.workspace(), dry_run=self.schmenkins.dry_run)

                run_cmd(['git', 'fetch', remote_name],
                         cwd=self.workspace(), dry_run=self.schmenkins.dry_run)

                rev = self.build_revision or '%s/%s' % (remote_name, git.get('branch', 'master'))
                run_cmd(['git', 'reset', '--hard', rev], cwd=self.workspace(), dry_run=self.schmenkins.dry_run)

    def build(self, build):
        builders = self._job_dict.get('builders', [])
        for builder in builders:
            for builder_type in builder:
                if builder_type == 'shell':
                    with tempfile.NamedTemporaryFile(delete=False) as fp:
                        try:
                            os.chmod(fp.name, 0o0700)
                            fp.write(builder[builder_type])
                            fp.close()

                            maybe_shebang = builder[builder_type].split('\n')[0]

                            if maybe_shebang.startswith('#!'):
                                cmd = maybe_shebang[2:].split(' ')
                            else:
                                cmd = [os.environ.get('SHELL', '/bin/sh'), '-ex']

                            cmd += [fp.name]

                            run_cmd(cmd, cwd=self.workspace(), dry_run=self.schmenkins.dry_run)
                        finally:
                            os.unlink(fp.name)
                elif builder_type == 'copyartifacts':
                    copyartifacts = builder[builder_type]
                    source_job = SchmenkinsJob(self.schmenkins,
                                               self.schmenkins.jobs[itpl(copyartifacts['project'],
                                                                         build.parameters())])
                    if copyartifacts['which-build'] == 'specific-build':
                        source_build = SchmenkinsBuild(source_job,
                                                       build_number=itpl(copyartifacts['build-number'],
                                                                         build.parameters()))

                    else:
                        raise UnsupportedConfig(copyartifacts['which-build'])

                    target_dir = self.workspace()

                    if 'target' in copyartifacts:
                        target_dir = os.path.join(target_dir, copyartifacts['target'])

                    ensure_dir(target_dir)

                    source_dir = source_build.artifact_dir()

                    fileset = formic.FileSet(directory=source_dir,
                                             include=copyartifacts['filter'])

                    for f in fileset.qualified_files(absolute=False):
                        shutil.copy(os.path.join(source_dir, f),
                                    os.path.join(target_dir, f))

                else:
                    raise UnsupportedConfig('%s, %r' % (builder_type, builder[builder_type]))

    def publish(self, build):
        publishers = self._job_dict.get('publishers', [])
        for publisher in publishers:
            for publisher_type in publisher:
                if publisher_type == 'archive':
                    workspace = self.workspace()
                    artifact_dir = build.artifact_dir()

                    artifacts = publisher[publisher_type]['artifacts']
                    oldpath = os.getcwd()

                    os.chdir(workspace)

                    files = []
                    for artifact in artifacts.split(','):
                        files += glob(artifact)

                    os.chdir(oldpath)

                    for f in files:
                        shutil.copy(os.path.join(workspace, f), os.path.join(artifact_dir, f))
                elif publisher_type == 'trigger-parameterized-builds':
                    for trigger_build in publisher[publisher_type]:

                        if trigger_build['project'] not in self.schmenkins.jobs:
                            raise Exception('Unknown job %s' % (trigger_build['project'],))

                        if 'condition' in trigger_build:
                            if trigger_build['condition'] == 'UNSTABLE_OR_BETTER':
                                if self.state == 'FAILED':
                                    continue
                            else:
                                raise UnsupportedConfig('%s' % (trigger_build['condition'],))

                        parameters = {}

                        for l in trigger_build['predefined-parameters'].split('\n'):
                             if '=' not in l:
                                 continue
                             k, v = l.split('=', 1)
                             parameters[k] = itpl(v, build.parameters())

                        trigger_job = SchmenkinsJob(self.schmenkins,
                                                    self.schmenkins.jobs[trigger_build['project']])
                        triggered_build = trigger_job.run(parameters=parameters)
                else:
                    raise UnsupportedConfig('%s, %r' % (publisher_type, publisher[publisher_type]))


class Schmenkins(object):
    def __init__(self, basedir, cfgfile, ignore_timestamp=False, dry_run=False):
        self.basedir = basedir
        self.cfgfile = cfgfile
        self.ignore_timestamp = ignore_timestamp
        self.dry_run = dry_run
        self.state = SchmenkinsState()
        self.load_state()
        self.builder = self.get_builder()
        self.builder.load_files(self.cfgfile)
        self.builder.parser.expandYaml(None)

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

    def ensure_basedir(self):
        if not os.path.isdir(self.basedir):
            os.makedirs(self.basedir)

    def state_file(self):
        self.ensure_basedir()
        return os.path.join(self.basedir, 'state.json')

    def load_state(self):
        self.state.load(self.state_file())

    def save_state(self):
        self.state.save(self.state_file())

    def jobs_dir(self):
        return os.path.join(self.basedir, 'jobs')

    def handle_job(self, job_dict):
        job = SchmenkinsJob(self, job_dict)

        job.process_triggers()

        if job.should_poll and not job.should_run:
            job.poll()

        if job.should_run:
            job.run()


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

    schmenkins = Schmenkins(args.basedir, args.config, args.ignore_timestamp, args.dry_run)

    for job in schmenkins.jobs:
        if args.jobs and not any([fnmatch(job, job_glob) for job_glob in args.jobs]):
            logging.info('Skipping job: %s' % (job,))
            continue

        logging.info('Handling job: %s' % (job,))
        schmenkins.handle_job(schmenkins.jobs[job])

    schmenkins.state.last_run = time.mktime(schmenkins.now.timetuple())
    schmenkins.save_state()

if __name__ == '__main__':
    sys.exit(not main())

