from builder import hooks
from builder.tests.utils import PatchCase


class SetupCase(PatchCase):
    mocks = {
        "chdir": "os.chdir",
        "isdir": "os.path.isdir",
        "call": "subprocess.call"
    }

    def test_pwd_changed(self):
        hooks.setup("path")
        self.mock_chdir.assert_called_with("path")

    def test_called_when_dir(self):
        self.mock_isdir.return_value = True
        hooks.setup("path")
        self.mock_isdir.assert_called_with("hooks")
        self.mock_call.assert_called_with(['chmod', '-R', '+x', 'hooks'])

    def test_skipped_when_not_dir(self):
        self.mock_isdir.return_value = False
        hooks.setup("path")
        self.mock_isdir.assert_called_with("hooks")
        assert self.mock_call.called is False


class RunCase(PatchCase):
    mocks = {
        "log": "builder.hooks.public_log",
        "isfile": "os.path.isfile",
        "execute": "builder.utils.execute_command"
    }

    def test_called_when_file(self):
        self.mock_isfile.return_value = True
        assert hooks.run("name")
        self.mock_execute.assert_called_with("hooks/name", "name hook failed!")

    def test_skipped_when_not_file(self):
        self.mock_isfile.return_value = False
        assert not hooks.run("name")
        assert self.mock_execute.called is False
