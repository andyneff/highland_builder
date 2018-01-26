import mock

from builder import build, errors
from builder.tests.utils import PatchCase


class LogDockerVersionCase(PatchCase):
    mocks = {'log': 'builder.build.public_log'}

    def mockUp(self):
        self.mock_version = mock.MagicMock(return_value=dict(a=1, b=2, c=3))
        self.mock_client = mock.MagicMock(version=self.mock_version)

    def test_version_items(self):
        build.log_docker_version(self.mock_client)
        assert mock.call("a: 1") in self.mock_log.info.call_args_list
        assert mock.call("b: 2") in self.mock_log.info.call_args_list
        assert mock.call("c: 3") in self.mock_log.info.call_args_list


class ProcessStreamLineCase(PatchCase):
    mocks = {'log': 'builder.build.public_log'}

    def test_str_logged(self):
        build.process_stream_line({'stream': '<value>'})
        self.mock_log.info.assert_called_with('<value>', end='')

    def test_unicode_logged(self):
        build.process_stream_line({'stream': unicode('<value>')})
        self.mock_log.info.assert_called_with('<value>', end='')

    def test_none_unlogged(self):
        build.process_stream_line({'stream': None})
        assert self.mock_log.info.called is False


class ProcessErrorLineCase(PatchCase):
    mocks = {'log': 'builder.build.public_log'}

    def test_str_raised(self):
        with self.assertRaises(errors.HighlandError):
            build.process_error_line({'error': '<value>'})

    def test_unicode_raised(self):
        with self.assertRaises(errors.HighlandError):
            build.process_error_line({'error': unicode('<value>')})

    def test_none_unraised(self):
        build.process_error_line({'error': None})


class BuildImageCase(PatchCase):
    mocks = {'log': 'builder.build.public_log'}

    def mockUp(self):
        self.mock_client = mock.MagicMock()

    def default_build_args(self):
        return dict(
            path='<build_path>',
            dockerfile='<dockerfile>',
            tag='<tag>',
            nocache=True,
            pull=True,
            decode=True,
            stream=True,
            rm=True,
            forcerm=True)

    def test_build_args(self):
        build.build_image(self.mock_client, '<build_path>', '<dockerfile>',
                          '<tag>')
        self.mock_client.build.assert_called_with(**self.default_build_args())

    def test_use_cache(self):
        build.build_image(
            self.mock_client,
            '<build_path>',
            '<dockerfile>',
            '<tag>',
            cache_repo='<cache_repo>')
        build_args = self.default_build_args()
        build_args['nocache'] = False
        build_args['cache_from'] = ['<cache_repo>']
        self.mock_client.build.assert_called_with(**build_args)

    @mock.patch('builder.build.process_stream_line')
    def test_stream_line(self, mock_stream_line):
        self.mock_client.build.return_value = ['stream-1', 'stream-2']
        build.build_image(self.mock_client, None, None, None)
        assert mock_stream_line.call_args_list == [
            mock.call('stream-1'), mock.call('stream-2')
        ]

    @mock.patch('builder.build.process_error_line')
    def test_stream_error(self, mock_stream_line):
        self.mock_client.build.return_value = ['error-1', 'error-2']
        build.build_image(self.mock_client, None, None, None)
        assert mock_stream_line.call_args_list == [
            mock.call('error-1'), mock.call('error-2')
        ]


class MultitagImageCase(PatchCase):
    def test_all_tagged(self):
        mock_client = mock.MagicMock()
        build.multitag_image(mock_client, 'image', 'repo', ['tag1', 'tag2'])
        assert mock_client.tag.call_args_list == [
            mock.call('image', 'repo', 'tag1'), mock.call('image', 'repo',
                                                          'tag2')
        ]


class AddThisTagCase(PatchCase):
    def test_this_tagged(self):
        mock_client = mock.MagicMock()
        build.add_this_tag(mock_client, 'image')
        mock_client.tag.assert_called_with('image', 'this', force=True)
