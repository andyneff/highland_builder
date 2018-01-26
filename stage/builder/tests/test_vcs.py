import os
import mock

from builder import vcs, errors
from builder.tests.utils import PatchCase


class ProcessSourceUrlCase(PatchCase):
    def test_no_prefix(self):
        assert "foo" == vcs.process_source_url("foo")

    def test_github_prefix(self):
        url = "https://github.com/foo/bar/"
        result = vcs.process_source_url(url)
        assert result == "git@github.com:foo/bar/"


class WritePrivateKeyCase(PatchCase):

    mocks = {'chmod': 'os.chmod', 'open': '__builtin__.open'}

    @mock.patch("os.path.expanduser")
    def test_expanduser(self, mock_expanduser):
        vcs.write_private_key("key")
        mock_expanduser.assert_called_with("~/.ssh/id_rsa")

    def test_contents_written(self):
        vcs.write_private_key("key")
        self.mock_open.assert_called_with("/root/.ssh/id_rsa", "w")
        fobj = mock.call().__enter__()
        assert fobj.write("key") in self.mock_open.mock_calls
        assert fobj.write("\n") in self.mock_open.mock_calls

    def test_change_destination(self):
        vcs.write_private_key("key", "/root/foo/id_rsa")
        self.mock_open.assert_called_with("/root/foo/id_rsa", "w")

    def test_change_mode(self):
        vcs.write_private_key("key", mode=0666)
        self.mock_chmod.assert_called_with("/root/.ssh/id_rsa", 0666)


class CloneCommandsForGitCase(PatchCase):
    def test_commit(self):
        commands = vcs.clone_commands_for_git("url", "branch", "commit", "bin")
        joined = [" ".join(c) for c in commands]
        assert joined == [
            "bin clone --recursive url .", "bin checkout -B branch commit",
            "bin submodule update"
        ]

    def test_commit_no_branch(self):
        commands = vcs.clone_commands_for_git("url", None, "commit", "bin")
        joined = [" ".join(c) for c in commands]
        assert joined == [
            "bin clone --recursive url .", "bin checkout -B master commit",
            "bin submodule update"
        ]

    def test_no_commit(self):
        commands = vcs.clone_commands_for_git("url", "branch", bin_path="bin")
        joined = [" ".join(c) for c in commands]
        assert joined == [
            "bin clone --recursive --depth 1 -b branch url .",
            "bin submodule update",
        ]

    def test_no_commit_no_branch(self):
        commands = vcs.clone_commands_for_git("url", None, bin_path="bin")
        joined = [" ".join(c) for c in commands]
        assert joined == [
            "bin clone --recursive --depth 1 -b master url .",
            "bin submodule update",
        ]


class CloneCommandsForHgCase(PatchCase):
    def test_branch(self):
        commands = vcs.clone_commands_for_hg("url", "branch", "commit", "bin")
        joined = [" ".join(c) for c in commands]
        assert joined == ["bin clone -r branch url ."]

    def test_no_branch(self):
        commands = vcs.clone_commands_for_hg("url", None, "commit", "bin")
        joined = [" ".join(c) for c in commands]
        assert joined == ["bin clone -r default url ."]


class GetCloneCommandsCase(PatchCase):
    def test_wrong_source_type(self):
        with self.assertRaises(errors.HighlandError):
            vcs.get_clone_commands("foo", "url", "branch")

    @mock.patch("builder.vcs.clone_commands_for_git")
    def test_git_delegate(self, mock_git):
        vcs.get_clone_commands("git", "url", "branch", "commit")
        mock_git.assert_called_with("url", "branch", "commit")

    @mock.patch("builder.vcs.clone_commands_for_hg")
    def test_hg_delegate(self, mock_hg):
        vcs.get_clone_commands("hg", "url", "branch", "commit")
        mock_hg.assert_called_with("url", "branch", "commit")


class ConvertCloneErrorCase(PatchCase):
    def test_access_rights(self):
        msg = vcs.convert_clone_error(vcs.ACCESS_RIGHTS_SUBSTR)
        assert msg == (
            'please ensure the correct public key is added to the list of trusted '
            'keys for this repository')

    def test_no_branch(self):
        msg = vcs.convert_clone_error(vcs.NO_BRANCH_SUBSTR)
        assert msg == 'please ensure the remote branch exists'

    def test_no_match(self):
        msg = vcs.convert_clone_error("")
        assert msg == (
            'please ensure the correct public key is added to the list of trusted '
            'keys for this repository and the remote branch exists.')


class ExportGitDetailsCase(PatchCase):
    mocks = {"output": "builder.utils.get_output"}

    def mockUp(self):
        self.mock_output.return_value = "output"
        environ_patch = mock.patch("os.environ", dict())
        self.mock_environ = environ_patch.start()
        self.addCleanup(environ_patch.stop)

    def test_sha1(self):
        vcs.export_git_details()
        assert self.mock_output.call_args_list == [
            mock.call(['git', 'rev-parse', 'HEAD']),
            mock.call(['git', 'log', '--format=%B', '-n', '1', 'output']),
        ]
        assert os.environ['GIT_SHA1'] == 'output'
        assert os.environ['GIT_MSG'] == 'output'
        assert os.environ['COMMIT_MSG'] == 'output'


class CloneCase(PatchCase):
    mocks = {
        "key": "builder.vcs.write_private_key",
        "commands": "builder.vcs.get_clone_commands",
        "execute": "builder.utils.execute_command",
        "export": "builder.vcs.export_git_details",
        "public_log": "builder.vcs.public_log"
    }

    def mockUp(self):
        environ_patch = mock.patch("os.environ", dict())
        self.mock_environ = environ_patch.start()
        self.addCleanup(environ_patch.stop)
        self.mock_environ['SOURCE_URL'] = True

    def test_private_key(self):
        vcs.clone("git", "url", "branch", private_key="key")
        assert self.mock_key.called

    def test_no_private_key(self):
        vcs.clone("git", "url", "branch")
        assert self.mock_key.called is False

    def test_clone_executed(self):
        self.mock_commands.return_value = "a", "b", "c"
        vcs.clone("git", "url", "branch")
        self.mock_commands.assert_called_with("git", "url", "branch", None)
        assert self.mock_execute.call_args_list == [
            mock.call("a", vcs.convert_clone_error),
            mock.call("b", vcs.convert_clone_error),
            mock.call("c", vcs.convert_clone_error),
        ]

    def test_git_details_exported(self):
        vcs.clone("git", "url", "branch")
        assert self.mock_export.called

    def test_git_details_unexported(self):
        vcs.clone("hg", "url", "branch")
        assert self.mock_export.called is False

    def test_source_url_deleted(self):
        vcs.clone("hg", "url", "branch")
        assert "SOURCE_URL" not in self.mock_environ
