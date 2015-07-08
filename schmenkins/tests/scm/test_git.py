import mock
import unittest

import schmenkins.scm.git

class GitTests(unittest.TestCase):
    def setUp(self):
        self.schmenkins = mock.MagicMock()
        self.schmenkins.dry_run = mock.sentinel.DRY_RUN
        self.job = mock.MagicMock()
        self.build = mock.MagicMock()
        self.build.logger = mock.sentinel.logger
        self.job.name = 'testjobname'
        self.job.build_revision = None
        self.job.should_run = False

    def test_poll_default_master_branch(self):
        self._test_poll('sha1', True)

    def test_poll_other_branch(self):
        self._test_poll('sha2', True, branch='other_branch')

    def test_poll_no_changes(self):
        self.job.state.last_seen_revision = 'sha2'
        self._test_poll('sha2', False, branch='other_branch')

    @mock.patch('schmenkins.scm.git.LOG')
    def test_poll_unknown_branch(self, log):
        self._test_poll(None, False, branch='unknown_branch')
        log.error.assert_called_with('Did not find revision for '
                                     'refs/heads/unknown_branch for job '
                                     'testjobname')

    @mock.patch('schmenkins.scm.git.run_cmd')
    def _test_poll(self, expected_revision, should_run, run_cmd, branch=None):
        url = 'https://github.com/something/else.git'
        info = {'url': url}

        if branch:
            info['branch'] = branch

        def fake_run_cmd(cmd, **kwargs):
            if cmd[0] == 'git':
                if cmd[1] == 'ls-remote':
                    self.assertEquals(cmd[2], url)
                    return '\n'.join(['sha1 refs/heads/master',
                                      'sha2 refs/heads/other_branch'])

        run_cmd.side_effect = fake_run_cmd

        schmenkins.scm.git.poll(self.schmenkins, self.job, info)
        run_cmd.assert_any_call(['git', 'ls-remote', url], dry_run=self.schmenkins.dry_run)
        self.assertEquals(self.job.build_revision, expected_revision)
        self.assertEquals(self.job.should_run, should_run)

    @mock.patch('shutil.rmtree')
    @mock.patch('schmenkins.scm.git.run_cmd')
    def test_checkout(self, run_cmd, rmtree):
        url = 'https://github.com/something/else.git'
        info = {'url': url}

        self.build.build_revision = 'thissha'
        self.build._parameters = {}

        self.job.workspace.return_value = 'workspacedir'

        def fake_run_cmd(cmd, **kwargs):
            if cmd == ['git', 'rev-parse', 'HEAD']:
                return 'parsed_sha'
            elif cmd == ['git', 'log', '-1', '--oneline']:
                return 'deadbeef Some changes\n'

        run_cmd.side_effect = fake_run_cmd

        schmenkins.scm.git.checkout(self.schmenkins, self.job, info, self.build)
        rmtree.assert_called_with('workspacedir')

        print run_cmd.call_args_list
        run_cmd.assert_any_call(['git', 'init'], cwd='workspacedir',
                                logger=mock.sentinel.logger, dry_run=mock.sentinel.DRY_RUN)
        run_cmd.assert_any_call(['git', 'remote', 'add', 'origin', url],
                                logger=mock.sentinel.logger, cwd='workspacedir', dry_run=mock.sentinel.DRY_RUN)
        run_cmd.assert_any_call(['git', 'remote', 'set-url', 'origin', url],
                                logger=mock.sentinel.logger, cwd='workspacedir', dry_run=mock.sentinel.DRY_RUN)
        run_cmd.assert_any_call(['git', 'fetch', 'origin'],
                                logger=mock.sentinel.logger, cwd='workspacedir', dry_run=mock.sentinel.DRY_RUN)
        run_cmd.assert_any_call(['git', 'reset', '--hard', 'thissha'],
                                logger=mock.sentinel.logger, cwd='workspacedir', dry_run=mock.sentinel.DRY_RUN)
        self.assertEquals(self.build._parameters['GIT_COMMIT'], 'parsed_sha')

    @mock.patch('shutil.rmtree')
    @mock.patch('schmenkins.scm.git.run_cmd')
    def test_checkout_does_not_wipe_workspace(self, run_cmd, rmtree):
        url = 'https://github.com/something/else.git'
        info = {'url': url,
                'wipe-workspace': False}

        self.build.build_revision = 'thissha'
        self.build._parameters = {}

        self.job.workspace.return_value = 'workspacedir'

        def fake_run_cmd(cmd, **kwargs):
            if cmd == ['git', 'rev-parse', 'HEAD']:
                return 'parsed_sha'
            elif cmd == ['git', 'log', '-1', '--oneline']:
                return 'deadbeef Some changes\n'

        run_cmd.side_effect = fake_run_cmd

        schmenkins.scm.git.checkout(self.schmenkins, self.job, info, self.build)
 
        self.assertEquals(rmtree.call_count, 0)
