import errno
import subprocess

import mock

from builder import utils, errors
from builder.tests.utils import PatchCase, easy_dict


class CleanPathCase(PatchCase):
    def test_absolute_path(self):
        dirty_path = "/foo"
        assert "./foo" == utils.clean_path(dirty_path)

    def test_relative_unforced(self):
        dirty_path = "/foo"
        assert "foo" == utils.clean_path(dirty_path, force_relative=False)


class GetOutputCase(PatchCase):
    mocks = {'popen': 'subprocess.Popen'}

    def mockUp(self):
        self.mock_communicate = mock.MagicMock()
        self.mock_proc = mock.MagicMock(communicate=self.mock_communicate)
        self.mock_popen.return_value = self.mock_proc

    def test_result(self):
        self.mock_communicate.return_value = ["stdoutdata\n", "stderrdata\n"]
        assert utils.get_output(None) == "stdoutdata"


class ExecuteCommandCase(PatchCase):

    mocks = {
        'popen': 'subprocess.Popen',
        'public_log': 'builder.utils.public_log'
    }

    def mockUp(self):
        self.mock_handler = mock.MagicMock()
        self.mock_wait = mock.MagicMock(return_value=0)
        self.mock_readline = mock.MagicMock(side_effect=[])
        self.mock_proc = mock.MagicMock(wait=self.mock_wait)
        self.mock_proc.stdout.readline = self.mock_readline
        self.mock_popen.return_value = self.mock_proc

    def test_popen_args(self):
        utils.execute_command('command', self.mock_handler)
        self.mock_popen.assert_called_with(
            'command',
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1)

    def test_logged_output(self):
        self.mock_readline.side_effect = ["1", "2", "3"]
        utils.execute_command('command', self.mock_handler)
        assert self.mock_public_log.info.call_args_list == [
            mock.call("1"), mock.call("2"), mock.call("3")
        ]

    def test_error_handling(self):
        self.mock_readline.side_effect = ["1", "2", "3"]
        self.mock_wait.return_value = 1
        with self.assertRaises(errors.HighlandError):
            utils.execute_command('command', self.mock_handler)
        self.mock_handler.assert_called_with("123")

    def test_skipped_handling(self):
        self.mock_handler = mock.NonCallableMock()
        self.mock_readline.side_effect = ["1", "2", "3"]
        self.mock_wait.return_value = 1
        with self.assertRaises(errors.HighlandError):
            utils.execute_command('command', self.mock_handler)
        assert self.mock_handler.called is False

    def test_error_message_for_missing_shbang(self):
        def side_effect(*args, **kwargs):
            oerr = OSError()
            oerr.errno = errno.ENOEXEC
            raise oerr

        self.mock_popen.side_effect = side_effect
        with self.assertRaises(errors.HighlandError) as herr:
            utils.execute_command('./path/to/command', self.mock_handler)
        self.mock_popen.assert_called_with(
            './path/to/command',
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1)
        expected_msg = "Could not execute hook at './path/to/command'. Is it missing a #! line?"
        self.assertEqual(herr.exception.args[0], expected_msg)


class CleanLogAttrCase(PatchCase):
    def test_string(self):
        assert utils.clean_log_attr(unicode("foo")) == "foo"

    def test_non_string(self):
        assert utils.clean_log_attr(100) == "100"


class PostToUrlCase(PatchCase):
    mocks = {
        'open': '__builtin__.open',
        'post': 'requests.post',
        'public_log': 'builder.utils.public_log',
        'private_log': 'builder.utils.private_log'
    }

    def mockUp(self):
        self.mock_fobj = mock.MagicMock()
        self.mock_open.return_value = self.mock_fobj
        self.post_spec = easy_dict('url', 'fields')

    def test_no_spec(self):
        assert utils.post_to_url(None, None) is None

    def test_returns_true(self):
        self.mock_post.return_value = mock.MagicMock(status_code=204)
        assert utils.post_to_url(self.post_spec, None)

    def test_cant_post(self):
        self.mock_post.return_value = mock.MagicMock(status_code=404, text='')
        with self.assertRaises(Exception):
            utils.post_to_url(self.post_spec, None)
        assert self.mock_private_log.info.call_args_list == [
            mock.call(
                "post error", code=404, text=''),
        ] * 5


class FetchFromUrlCase(PatchCase):
    mocks = {
        'open': '__builtin__.open',
        'get': 'requests.get',
        'public_log': 'builder.utils.public_log'
    }

    def mockUp(self):
        self.mock_fobj = mock.MagicMock()
        self.mock_open.return_value = self.mock_fobj

    def test_no_url(self):
        assert utils.fetch_from_url(None, None) is None

    def test_returns_true(self):
        self.mock_get.return_value = mock.MagicMock(status_code=200)
        assert utils.fetch_from_url('<url>', '<path>')

    def test_logs_exception(self):
        self.mock_get.side_effect = Exception('<test>')
        utils.fetch_from_url('<url>', '<path>')
        self.mock_public_log.info.assert_called_with(
            'Warning: Exception while downloading <path> from <url>')
