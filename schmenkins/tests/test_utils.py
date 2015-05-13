import mock
import os
import shutil
import tempfile

from schmenkins import exceptions
from schmenkins import utils
from schmenkins import tests


class TestUtils(tests.SchmenkinsTest):
    def test_itpl(self):
        d = {'abc': 'def',
             'AbC': 'ghi'}

        self.assertEquals(utils.itpl('123${abc}456', d), '123def456')
        self.assertEquals(utils.itpl('123${AbC}456', d), '123ghi456')
        self.assertEquals(utils.itpl('123${Ab}456', d), '123456')
        self.assertEquals(utils.itpl('123$Ab456', d), '123')
        self.assertEquals(utils.itpl('123$AbC456', d), '123')
        self.assertEquals(utils.itpl('123$AbC', d), '123ghi')

    def test_run_cmd(self):
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            try:
                fp.close()
                utils.run_cmd(['bash', '-c', 'echo -n hello > %s' % (fp.name,)])
                self.assertEquals(open(fp.name, 'r').read(), 'hello')
            finally:
                os.unlink(fp.name)

    def test_run_cmd_dry_run(self):
        with tempfile.NamedTemporaryFile(delete=False) as fp:
            try:
                fp.close()
                utils.run_cmd(['bash', '-c', 'echo -n hello > %s' % (fp.name,)],
                               dry_run=True)
                self.assertEquals(open(fp.name, 'r').read(), '')
            finally:
                os.unlink(fp.name)

    def test_run_cmd_output(self):
        mock_logger = mock.MagicMock()
        output = utils.run_cmd(['bash', '-c', 'echo -n hello'])
        self.assertEquals(output, 'hello')

    def test_run_cmd_logging(self):
        mock_logger = mock.MagicMock()
        output = utils.run_cmd(['bash', '-c', 'echo -n hello'],
                                logger=mock_logger)
        mock_logger.debug.assert_called_with('hello')
        self.assertEquals(output, 'hello')

    def test_run_cmd_failure(self):
        self.assertRaises(exceptions.SchmenkinsCommandFailed,
                          utils.run_cmd, ['false'])

    def test_ensure_dir(self):
        tmpdir = tempfile.mkdtemp()
        try:
            path = os.path.join(tmpdir, 'onemorelevel')
            utils.ensure_dir(path)
            self.assertTrue(os.path.isdir(path))

            # Test for idempotency
            utils.ensure_dir(path)
        finally:
            shutil.rmtree(tmpdir)

    @mock.patch('schmenkins.utils.ensure_dir')
    def test_ensure_dir_wrapper(self, ensure_dir):
        @utils.ensure_dir_wrapper
        def somedir(foo, bar='baz'):
            self.assertEquals(foo, 'wibble')
            self.assertEquals(bar, 'wobble')
            return 'fakedir'

        somedir('wibble', bar='wobble')
        ensure_dir.assert_called_with('fakedir')

