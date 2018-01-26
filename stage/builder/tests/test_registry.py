import mock

from builder import registry, errors
from builder.tests.utils import PatchCase, easy_dict


class HandleProgressCase(PatchCase):
    def test_no_prefix(self):
        push_line = easy_dict('id', 'progress')
        push_line['progressDetail'] = easy_dict('current', 'total')
        result = registry.handle_progress(push_line)
        assert result == "<id> Pushing: <progress> <current>/<total>"

    def test_no_progressdetail(self):
        # TODO make handle_progress actually do something other than raise
        # AttributeError if the struct is malformed
        push_line = easy_dict('id', 'progress')
        with self.assertRaises(AttributeError):
            registry.handle_progress(push_line)


class HandleIdCase(PatchCase):
    def test_result(self):
        assert "<id>: <status>" == registry.handle_id(
            easy_dict('id', 'status'))


class HandleStatusCase(PatchCase):

    mocks = {
        'progress': 'builder.registry.handle_progress',
        'id': 'builder.registry.handle_id'
    }

    def handle_status(self, status):
        line = {'status': status}
        registry.handle_status(line)
        return line

    def test_pushing(self):
        line = self.handle_status("Pushing")
        self.mock_progress.assert_called_with(line)
        assert self.mock_id.called is False

    def test_waiting(self):
        line = self.handle_status('Waiting')
        self.mock_id.assert_called_with(line)
        assert self.mock_progress.called is False

    def test_preparing(self):
        line = self.handle_status('Preparing')
        self.mock_id.assert_called_with(line)
        assert self.mock_progress.called is False

    def test_pushed(self):
        line = self.handle_status('Pushed')
        self.mock_id.assert_called_with(line)
        assert self.mock_progress.called is False

    def test_novel(self):
        self.handle_status('foobar')
        assert self.mock_progress.called is False
        assert self.mock_id.called is False


class HandleRawStatusCase(PatchCase):
    def test_wrong_keys(self):
        assert registry.handle_raw_status(easy_dict('status', 'foo')) is None

    def test_correct_keys(self):
        assert '<status>' == registry.handle_raw_status(easy_dict('status'))


class HandleAuxProgressCase(PatchCase):
    def test_wrong_keys(self):
        assert not registry.handle_aux_progress(easy_dict('foo', 'aux'))

    def test_wrong_structure(self):
        assert not registry.handle_aux_progress(
            easy_dict('aux', 'progressDetail'))

    def test_match(self):
        push_line = {'progressDetail': None, 'aux': easy_dict('foo', 'bar')}
        result = registry.handle_aux_progress(push_line)
        assert result == "  foo: <foo>\n  bar: <bar>"


class FormatStreamLineCase(PatchCase):

    mocks = {
        'loads': 'json.loads',
        'status': 'builder.registry.handle_status',
        'raw': 'builder.registry.handle_raw_status',
        'aux': 'builder.registry.handle_aux_progress'
    }

    def test_calls(self):
        self.mock_loads.return_value = 'loads'
        registry.format_stream_line(None)
        self.mock_loads.assert_called_with(None)
        self.mock_status.assert_called_with('loads')
        self.mock_raw.assert_called_with('loads')
        self.mock_aux.assert_called_with('loads')

    def test_status_result(self):
        assert registry.format_stream_line(
            None)._mock_new_parent == self.mock_status

    def test_raw_result(self):
        self.mock_status.return_value = None
        assert registry.format_stream_line(
            None)._mock_new_parent == self.mock_raw

    def test_aux_result(self):
        self.mock_status.return_value = None
        self.mock_raw.return_value = None
        result = registry.format_stream_line(None)
        assert result._mock_new_parent == self.mock_aux

    def test_encoded_result(self):
        self.mock_status.return_value = None
        self.mock_raw.return_value = None
        self.mock_aux.return_value = None
        assert "encoded" == registry.format_stream_line("encoded")


class LogStreamLineCase(PatchCase):
    mocks = {
        "log": "builder.registry.private_log",
        "format": "builder.registry.format_stream_line"
    }

    def test_no_execption(self):
        self.mock_format.return_value = "format"
        registry.log_stream_line(None)
        self.mock_format.assert_called_with(None)
        self.mock_log.info.assert_called_with("format")

    def test_exception(self):
        self.mock_format.side_effect = Exception()
        registry.log_stream_line('line')
        self.mock_log.info.assert_called_with('line')


class RegistryOperation(PatchCase):
    mocks = {'log': 'builder.registry.log_stream_line', 'loads': 'json.loads'}

    def run_op(self, *lines):
        op = mock.MagicMock(return_value=lines)
        return registry.registry_operation(op, "repo", "tag")

    def test_lines_logged_and_parsed(self):
        self.run_op('a', 'b')
        assert self.mock_log.call_args_list == [mock.call('a'), mock.call('b')]
        assert self.mock_loads.call_args_list == [
            mock.call("a"), mock.call("b")
        ]

    def test_error_detail(self):
        self.mock_loads.return_value = easy_dict('errorDetail')
        assert "<errorDetail>" == self.run_op('a')

    def test_error(self):
        self.mock_loads.return_value = easy_dict('error')
        assert "<error>" == self.run_op('a')


class TryPushCase(PatchCase):
    mocks = {'op': 'builder.registry.registry_operation'}

    def mockUp(self):
        self.mock_client = mock.MagicMock()

    def test_no_tags(self):
        assert not registry.try_push(self.mock_client, "repo", [])

    def test_no_error(self):
        self.mock_op.return_value = None
        assert not registry.try_push(self.mock_client, "repo", "abc")

    def test_error(self):
        self.mock_op.return_value = "error"
        assert "error" == registry.try_push(self.mock_client, "repo", "abc")


class RetryDelayCase(PatchCase):
    mocks = {'log': 'builder.registry.public_log', 'sleep': 'time.sleep'}

    def test_positive(self):
        registry.retry_delay(1)
        self.mock_sleep.assert_called_with(60)

    def test_not_positive(self):
        registry.retry_delay(0)
        assert not self.mock_sleep.called


class PushCase(PatchCase):
    mocks = {
        'retry': 'builder.registry.retry_delay',
        'push': 'builder.registry.try_push'
    }

    def test_error(self):
        with self.assertRaises(errors.HighlandError):
            registry.push('client', 'repo', 'tags')
        assert self.mock_retry.call_count == 5

    def test_change_retries(self):
        with self.assertRaises(errors.HighlandError):
            registry.push('client', 'repo', 'tags', retry_count=1)
        assert self.mock_retry.call_count == 1

    def test_no_error(self):
        self.mock_push.return_value = None
        registry.push('client', 'repo', 'tags')
        assert self.mock_retry.call_count == 1


class PullCase(PatchCase):
    mocks = {
        'retry': 'builder.registry.retry_delay',
        'op': 'builder.registry.registry_operation',
        'public_log': 'builder.registry.public_log',
        'metrics': 'builder.registry.metrics'
    }

    def mockUp(self):
        self.mock_client = mock.MagicMock()

    def test_error(self):
        registry.pull(self.mock_client, 'repo', 'tag')
        assert self.mock_retry.call_count == 5

    def test_change_retries(self):
        registry.pull(self.mock_client, 'repo', 'tag', retry_count=1)
        assert self.mock_retry.call_count == 1

    def test_no_error(self):
        self.mock_op.return_value = None
        registry.pull(self.mock_client, 'repo', 'tag')
