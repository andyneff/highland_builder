import mock

from builder import startup, errors
from builder.tests.utils import PatchCase, patch_open


class LogBuildDestinationCase(PatchCase):

    mocks = {'log': 'builder.startup.public_log'}

    def test_byon(self):
        startup.log_build_destination('byon')
        assert "User Node" in self.mock_log.info.call_args_list[0][0][0]

    def test_infra(self):
        startup.log_build_destination(None)
        assert "Docker Cloud" in self.mock_log.info.call_args_list[0][0][0]


class PrepareBuildStage(PatchCase):
    mocks = {'chdir': 'os.chdir', 'makedirs': 'os.makedirs'}

    def test_calls(self):
        startup.prepare_build_stage('code')
        assert self.mock_chdir.call_args_list == [
            mock.call('/src'), mock.call('code')
        ]
        self.mock_makedirs.assert_called_with('code')


class DockerfileForFilePathCase(PatchCase):
    def test_no_dockerfile(self):
        assert "foo", "bar" == startup.dockerfile_for_file_path("foo/bar",
                                                                None)

    def test_dockerfile(self):
        assert "foo", "bar" == startup.dockerfile_for_file_path("foo/bar",
                                                                "bar")

    def test_dockerfile_conflict(self):
        with self.assertRaises(errors.HighlandError):
            startup.dockerfile_for_file_path("foo/bar", "baz")


class DockerfileForDirPath(PatchCase):
    mocks = {'isfile': 'os.path.isfile'}

    def test_no_dockerfile(self):
        assert "foo/bar", "Dockerfile" == startup.dockerfile_for_dir_path(
            "foo/bar", None)

    def test_dockerfile(self):
        assert "foo", "bar" == startup.dockerfile_for_dir_path("foo", "bar")

    def test_not_found_baz(self):
        self.mock_isfile.return_value = False
        with self.assertRaises(errors.HighlandError):
            startup.dockerfile_for_dir_path("foo/bar", "baz")

    def test_not_found_dockerfile(self):
        self.mock_isfile.return_value = False
        with self.assertRaises(errors.HighlandError):
            startup.dockerfile_for_dir_path("foo/bar", "Dockerfile")


class ResolveDockerfilePath(PatchCase):
    mocks = {
        'isfile': 'os.path.isfile',
        'isdir': 'os.path.isdir',
        'clean': 'builder.utils.clean_path',
        'for_file': 'builder.startup.dockerfile_for_file_path',
        'for_dir': 'builder.startup.dockerfile_for_dir_path'
    }

    def test_is_file(self):
        result = startup.resolve_dockerfile_path("path", "dockerfile")
        assert result._mock_new_parent == self.mock_for_file

    def test_is_dir(self):
        self.mock_isfile.return_value = False
        result = startup.resolve_dockerfile_path("path", "dockerfile")
        assert result._mock_new_parent == self.mock_for_dir

    def test_is_missing(self):
        self.mock_isfile.return_value = False
        self.mock_isdir.return_value = False
        with self.assertRaises(errors.HighlandError):
            startup.resolve_dockerfile_path("path", "dockerfile")


class ResolveReadmePath(PatchCase):

    mocks = {'glob': 'glob.glob', 'log': 'builder.startup.public_log'}

    def test_first_candidate(self):
        self.mock_glob.return_value = ("a", "b", "c")
        readme_path = startup.resolve_readme_path("path1", "path2")
        assert "a" == readme_path

    def test_globs(self):
        self.mock_glob.return_value = []
        startup.resolve_readme_path("path1", "path2")
        assert self.mock_glob.call_args_list == [
            mock.call("path1/README.md"),
            mock.call("path1/[Rr][Ee][Aa][Dd][Mm][Ee]*"),
            mock.call("path2/README.md"),
            mock.call("path2/[Rr][Ee][Aa][Dd][Mm][Ee]*"),
            mock.call("./README.md"), mock.call("./[Rr][Ee][Aa][Dd][Mm][Ee]*")
        ]


class SnapshotTagsCase(PatchCase):
    def mockUp(self):
        self.mock_client = mock.MagicMock()
        self.mock_client.images.return_value = ({
            'RepoTags': ['a']
        }, {
            'RepoTags': ['b', 'c']
        }, {
            'RepoTags': ['c']
        })

    def test_tag_set(self):
        tags = startup.snapshot_tags(self.mock_client)
        assert tags == set(['a', 'b', 'c'])


class SnapshotContainersCase(PatchCase):
    def mockUp(self):
        self.mock_client = mock.MagicMock()
        self.mock_client.containers.return_value = ({
            'Id': 'a'
        }, {
            'Id': 'b'
        }, {
            'Id': 'c'
        })

    def test_id_set(self):
        ids = startup.snapshot_containers(self.mock_client)
        assert ids == set(['a', 'b', 'c'])


class WriteDockerCfgCase(PatchCase):
    @patch_open()
    def test_file_written(self, mock_open):
        startup.write_docker_cfg("content")
        mock_open.assert_has_calls(
            [mock.call('/root/.dockercfg', 'w'), mock.call().write('content')],
            any_order=True)

    @patch_open()
    def test_alternative_path(self, mock_open):
        startup.write_docker_cfg("content", path="/root/.dckr")
        assert mock.call('/root/.dckr', 'w') in mock_open.mock_calls


class LoginCase(PatchCase):
    mocks = {
        'write_cfg': 'builder.startup.write_docker_cfg',
        'client': 'docker.client',
        'auth': 'builder.startup.auth'
    }

    def test_login(self):
        c = startup.login('host')
        assert not self.mock_write_cfg.called
        self.mock_client.APIClient.assert_called_with(
            'host', version='auto', timeout=60 * 120)
        self.mock_auth.load_config.assert_called_with('/root/.dockercfg')
        assert c._auth_configs._mock_new_parent == self.mock_auth.load_config

    def test_write_config(self):
        startup.login('host', 'config')
        self.mock_write_cfg.assert_called_with('config')
