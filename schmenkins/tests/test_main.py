import datetime
import json
import mock
import os
import os.path
import shutil
import tempfile

import schmenkins
import schmenkins.exceptions
from schmenkins import tests

class SimpleTestState(schmenkins.State):
    attrs = ['justone']

class TestState(tests.SchmenkinsTest):
    def test_init(self):
        state = SimpleTestState(justone='abc', somethingelse='cde')
        self.assertEquals(state.justone, 'abc')
        self.assertRaises(AttributeError, getattr, state, 'somethingelse')

    def test_load(self):
        state = SimpleTestState()
        state.path = os.path.join(os.path.dirname(__file__), 'extraneous_state.json')
        self.assertEquals(state.justone, 'some value')
        self.assertRaises(AttributeError, getattr, state, 'invalid')

    def test_load_enoent(self):
        tmpdir = tempfile.mkdtemp()
        try:
            state = SimpleTestState()
            state.path = os.path.join(tmpdir, 'blah')
            self.assertEquals(state.justone, None)
        finally:
            shutil.rmtree(tmpdir)

    def test_save(self):
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            try:
                fp.close()

                state = SimpleTestState()
                state.path = fp.name
                state.justone = 'abc'
                state.somethingelse = 'def'
                state.save()
                self.assertEquals(json.load(open(fp.name, 'r')), {'justone': 'abc'})
            finally:
                os.unlink(fp.name)

class TestSchmenkins(tests.SchmenkinsTest):
    def setUp(self):
        self.statedir = tempfile.mkdtemp()
        _fd, self.cfgfile = tempfile.mkstemp()
        os.close(_fd)
        super(TestSchmenkins, self).setUp()

    def tearDown(self):
        shutil.rmtree(self.statedir)
        os.unlink(self.cfgfile)
        super(TestSchmenkins, self).tearDown()

    def test_basic_properties(self):
        s = schmenkins.Schmenkins(self.statedir, self.cfgfile)
        self.assertEquals(s.state_file(), os.path.join(self.statedir, 'state.json'))
        self.assertEquals(s.base_timestamp, datetime.datetime.fromtimestamp(0))
        self.assertTrue(abs(s.now - datetime.datetime.now()) < datetime.timedelta(seconds=1))

    @mock.patch('schmenkins.SchmenkinsJob')
    def test_handle_job_basic(self, SchmenkinsJob):
        s = schmenkins.Schmenkins(self.statedir, self.cfgfile)

        job_dict = {}

        job = SchmenkinsJob.return_value
        s.handle_job(job_dict)

        SchmenkinsJob.assert_called_with(s, job_dict)

    @mock.patch('schmenkins.SchmenkinsJob')
    def test_handle_job_force_build_skips_triggers_and_polling(self, SchmenkinsJob):
        s = schmenkins.Schmenkins(self.statedir, self.cfgfile)

        job_dict = {}

        job = SchmenkinsJob.return_value
        job.should_poll = False
        job.should_run = False
        s.handle_job(job_dict, force_build=True)

        job.process_triggers.assert_not_called()
        job.poll.assert_not_called()
        job.run.assert_called_with()

    @mock.patch('schmenkins.SchmenkinsJob')
    def test_handle_job_triggers_say_should_build_skips_poll(self, SchmenkinsJob):
        s = schmenkins.Schmenkins(self.statedir, self.cfgfile)

        job_dict = {}

        job = SchmenkinsJob.return_value
        job.should_poll = False
        job.should_run = False
        job.process_triggers.side_effect = lambda:[setattr(job, attr, True) for attr in ['should_poll', 'should_run']]
        s.handle_job(job_dict)

        job.process_triggers.assert_called_with()
        job.poll.assert_not_called()
        job.run.assert_called_with()

    @mock.patch('schmenkins.SchmenkinsJob')
    def test_handle_job_triggers_say_should_poll_no_changes(self, SchmenkinsJob):
        s = schmenkins.Schmenkins(self.statedir, self.cfgfile)

        job_dict = {}

        job = SchmenkinsJob.return_value
        job.should_poll = False
        job.should_run = False
        job.process_triggers.side_effect = lambda:setattr(job, 'should_poll', True)
        s.handle_job(job_dict)

        job.process_triggers.assert_called_with()
        job.poll.assert_called_with()
        job.run.assert_not_called()

    @mock.patch('schmenkins.SchmenkinsJob')
    def test_handle_job_triggers_say_should_poll_with_changes(self, SchmenkinsJob):
        s = schmenkins.Schmenkins(self.statedir, self.cfgfile)

        job_dict = {}

        job = SchmenkinsJob.return_value
        job.should_poll = False
        job.should_run = False

        job.process_triggers.side_effect = lambda:setattr(job, 'should_poll', True)
        job.poll.side_effect = lambda:setattr(job, 'should_run', True)
        s.handle_job(job_dict)

        job.process_triggers.assert_called_with()
        job.poll.assert_called_with()
        job.run.assert_called_with()

class TestSchmenkinsJob(tests.SchmenkinsTest):
    def setUp(self):
        self.statedir = tempfile.mkdtemp()
        _fd, self.cfgfile = tempfile.mkstemp()
        os.close(_fd)
        self.schmenkins = schmenkins.Schmenkins(self.statedir, self.cfgfile)
        super(TestSchmenkinsJob, self).setUp()

    def tearDown(self):
        shutil.rmtree(self.statedir)
        os.unlink(self.cfgfile)
        super(TestSchmenkinsJob, self).tearDown()

    def test_str(self):
        job = schmenkins.SchmenkinsJob(self.schmenkins, {'name': 'JobName'})
        self.assertEquals(str(job), 'JobName')

    def test_unknown_type(self):
        self.assertRaises(schmenkins.exceptions.UnsupportedConfig,
                          schmenkins.SchmenkinsJob, self.schmenkins, {'name': 'JobName',
                                                                      'project-type': 'something-strange'})

    def test_workspace(self):
        job = schmenkins.SchmenkinsJob(self.schmenkins, {'name': 'JobName'})
        expected_path = os.path.join(self.statedir, 'jobs', 'JobName', 'workspace')
        self.assertEquals(job.workspace(), expected_path)
        self.assertTrue(os.path.isdir(expected_path))

    def test_build_records(self):
        job = schmenkins.SchmenkinsJob(self.schmenkins, {'name': 'JobName'})
        expected_path = os.path.join(self.statedir, 'jobs', 'JobName', 'build_records')
        self.assertEquals(job.build_records(), expected_path)
        self.assertTrue(os.path.isdir(expected_path))

    def test_process_triggers(self):
        job = schmenkins.SchmenkinsJob(self.schmenkins, {'name': 'JobName'})
        job.process_triggers()

    def test_process_triggers_unknown_trigger(self):
        job = schmenkins.SchmenkinsJob(self.schmenkins,
                                       {'name': 'JobName', 'triggers': [{'fakeplugin': {}}]})
        self.assertRaises(schmenkins.exceptions.UnsupportedConfig,
                          job.process_triggers)

    def test_poll(self):
        job = schmenkins.SchmenkinsJob(self.schmenkins, {'name': 'JobName'})
        job.poll()

    def test_poll_unknown_scm(self):
        job = schmenkins.SchmenkinsJob(self.schmenkins,
                                       {'name': 'JobName', 'scm': [{'fakeplugin': {}}]})
        self.assertRaises(schmenkins.exceptions.UnsupportedConfig,
                          job.poll)

    def test_checkout(self):
        job = schmenkins.SchmenkinsJob(self.schmenkins, {'name': 'JobName'})
        build = schmenkins.SchmenkinsBuild(job, job.build_revision, {})
        job.checkout(build)

    def test_checkout_unknown_scm(self):
        job = schmenkins.SchmenkinsJob(self.schmenkins,
                                       {'name': 'JobName', 'scm': [{'fakeplugin': {}}]})
        build = schmenkins.SchmenkinsBuild(job, job.build_revision, {})
        self.assertRaises(schmenkins.exceptions.UnsupportedConfig,
                          job.checkout, build)

    def test_build(self):
        job = schmenkins.SchmenkinsJob(self.schmenkins, {'name': 'JobName'})
        build = schmenkins.SchmenkinsBuild(job, job.build_revision, {})
        job.build(build)

    def test_builder_unknown_builder(self):
        job = schmenkins.SchmenkinsJob(self.schmenkins,
                                       {'name': 'JobName', 'builders': [{'fakeplugin': {}}]})
        build = schmenkins.SchmenkinsBuild(job, job.build_revision, {})
        self.assertRaises(schmenkins.exceptions.UnsupportedConfig,
                          job.build, build)

    def test_publish(self):
        job = schmenkins.SchmenkinsJob(self.schmenkins, {'name': 'JobName'})
        build = schmenkins.SchmenkinsBuild(job, job.build_revision, {})
        job.publish(build)

    def test_publisher_unknown_publisher(self):
        job = schmenkins.SchmenkinsJob(self.schmenkins,
                                       {'name': 'JobName', 'publishers': [{'fakeplugin': {}}]})
        build = schmenkins.SchmenkinsBuild(job, job.build_revision, {})
        self.assertRaises(schmenkins.exceptions.UnsupportedConfig,
                          job.publish, build)


