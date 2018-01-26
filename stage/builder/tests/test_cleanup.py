import mock

from builder import cleanup
from builder.tests.utils import PatchCase


class RemoveBuildStageCase(PatchCase):
    mocks = {"isdir": "os.path.isdir", "rmtree": "shutil.rmtree"}

    def test_removed_dir(self):
        self.mock_isdir.return_value = True
        cleanup.remove_build_stage(None)
        assert self.mock_rmtree.called is True

    def test_nondir_ignored(self):
        self.mock_isdir.return_value = False
        cleanup.remove_build_stage(None)
        assert self.mock_rmtree.called is False


class RemoveBuildContainersCase(PatchCase):
    def mockUp(self):
        self.mock_client = mock.MagicMock()

    def test_bail_on_no_originals(self):
        cleanup.remove_build_containers(self.mock_client, None)
        assert self.mock_client.containers.called is False

    def test_containers_removed(self):
        containers = [dict(Id="a"), dict(Id="b")]
        self.mock_client.containers.return_value = containers
        cleanup.remove_build_containers(self.mock_client, set([]))
        assert self.mock_client.remove_container.call_args_list == [
            mock.call(
                "a", force=True), mock.call(
                    "b", force=True)
        ]

    def test_originals_skipped(self):
        original = dict(Id="a")
        introduced = dict(Id="b")
        self.mock_client.containers.return_value = original, introduced
        cleanup.remove_build_containers(self.mock_client,
                                        set([original["Id"]]))
        self.mock_client.remove_container.assert_called_with("b", force=True)

    def test_catches_exception(self):
        containers = [dict(Id="a"), dict(Id="b")]
        self.mock_client.containers.return_value = containers
        self.mock_client.remove_container.side_effect = Exception()
        cleanup.remove_build_containers(self.mock_client, set([]))


class RemoveBuildTagsCase(PatchCase):
    def mockUp(self):
        self.mock_client = mock.MagicMock()

    def test_bails_on_no_originals(self):
        cleanup.remove_build_tags(self.mock_client, None)
        assert self.mock_client.images.called is False

    def test_tags_removed(self):
        tags = dict(RepoTags=["a"]), dict(RepoTags=["b"])
        self.mock_client.images.return_value = tags
        cleanup.remove_build_tags(self.mock_client, set([]))
        assert self.mock_client.remove_image.call_args_list == [
            mock.call(
                "a", force=True),
            mock.call(
                "b", force=True),
        ]

    def test_originals_skipped(self):
        original = dict(RepoTags=["a"])
        introduced = dict(RepoTags=["b"])
        self.mock_client.images.return_value = original, introduced
        cleanup.remove_build_tags(self.mock_client, set(original["RepoTags"]))
        self.mock_client.remove_image.assert_called_with("b", force=True)

    def test_catches_exception(self):
        tags = [dict(RepoTags=["a"]), dict(RepoTags=["b"])]
        self.mock_client.images.return_value = tags
        self.mock_client.remove_tag.side_effect = Exception()
        cleanup.remove_build_containers(self.mock_client, set([]))
