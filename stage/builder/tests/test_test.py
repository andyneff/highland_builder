import mock

from builder import test
from builder.tests.utils import PatchCase


def test_container_name():
    assert "foo_sut_1" == test.container_name("foo")


class BuildTestStackCase(PatchCase):
    mocks = {'execute': 'builder.utils.execute_command'}

    def test_command(self):
        test.build_test_stack('path', 'code')
        cmd = "docker-compose -f path -p code build".split()
        msg = "building path"
        self.mock_execute.assert_called_with(cmd, msg)


class BootTestStackCase(PatchCase):

    mocks = {'execute': 'builder.utils.execute_command'}

    def test_command(self):
        test.boot_test_stack('path', 'code')
        cmd = "docker-compose -f path -p code up -d sut".split()
        msg = 'starting "sut" service in path'
        self.mock_execute.assert_called_with(cmd, msg)


class StreamTestsOutputCase(PatchCase):
    mocks = {'public_log': 'builder.test.public_log'}

    def mockUp(self):
        self.mock_client = mock.MagicMock()
        self.mock_client.logs.return_value = ['a', 'b']

    def test_data_logged(self):
        test.stream_test_output(self.mock_client, 'code')
        self.mock_client.logs.assert_called_with('code_sut_1', stream=True)
        self.mock_public_log.info.assert_has_calls(
            [mock.call('a'), mock.call('b')], any_order=True)


class WaitForTestCase(PatchCase):

    mocks = {'name': 'builder.test.container_name'}

    def mockUp(self):
        self.mock_name.return_value = 'name'
        self.mock_client = mock.MagicMock()

    def test_wait(self):
        result = test.wait_for_test(self.mock_client, 'code')
        self.mock_client.wait.assert_called_with('name')
        assert result._mock_new_parent == self.mock_client.wait


class RemoveTestStackCase(PatchCase):
    mocks = {'execute': 'builder.utils.execute_command'}

    def test_command(self):
        test.remove_test_stack('path', 'code')
        cmd = "docker-compose -f path -p code rm --force -v".split()
        self.mock_execute.assert_called_with(cmd)


class RunTestCase(PatchCase):
    mocks = {
        'build': 'builder.test.build_test_stack',
        'boot': 'builder.test.boot_test_stack',
        'stream': 'builder.test.stream_test_output',
        'wait': 'builder.test.wait_for_test',
        'remove': 'builder.test.remove_test_stack',
        'handle': 'builder.test.handle_test_result',
        'log': 'builder.test.public_log'
    }

    def mockUp(self):
        self.mock_wait.return_value = 'wait'
        self.mock_client = mock.MagicMock()

    def test_calls(self):
        test.run_test(self.mock_client, 'path', 'code')
        self.mock_build.assert_called_with('path', 'code')
        self.mock_boot.assert_called_with('path', 'code')
        self.mock_stream.assert_called_with(self.mock_client, 'code')
        self.mock_wait.assert_called_with(self.mock_client, 'code')
        self.mock_remove.assert_called_with('path', 'code')
        self.mock_handle.assert_called_with('wait', 'path')


class TestCase(PatchCase):
    mocks = {
        'run': 'builder.test.run_test',
        'glob': 'glob.glob',
        "public_log": "builder.test.public_log"
    }

    def mockUp(self):
        self.mock_client = mock.MagicMock()
        self.mock_glob.return_value = 'a', 'b'

    def test_tests_ran(self):
        test.test(self.mock_client, 'code')
        self.mock_glob.assert_called_with('*[.-]test.yml')
        self.mock_run.call_args_list == [
            mock.call(self.mock_client, 'a', 'code'),
            mock.call(self.mock_client, 'b', 'code'),
        ]
