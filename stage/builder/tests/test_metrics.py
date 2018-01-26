import mock

from builder.metrics import MetricsLogger
from builder.tests.utils import PatchCase


class MetricsLoggerCase(PatchCase):
    mocks = {
        'private_log': 'builder.metrics.private_log',
        'timer_manager': 'builder.metrics.TimedContextManagerDecorator',
        'getLogger': 'logging.getLogger'
    }

    def mockUp(self):
        self.mock_log = mock.MagicMock()
        self.mock_getLogger.return_value = self.mock_log
        self.mock_metrics = MetricsLogger()

    def test_init(self):
        assert self.mock_metrics._log == self.mock_log

    def test_emit(self):
        self.mock_metrics.emit(
            'method', metric_name='metric_name', arg='value')
        self.mock_log.info.assert_called_with(
            'builder_metric_name', method='method', arg='value')

    def test_guage(self):
        self.mock_metrics.emit = mock.MagicMock()
        self.mock_metrics.guage('name', 'value', tag='tag-value')
        self.mock_metrics.emit.assert_called_with(
            'guage',
            metric_name='name',
            value='value',
            sample_rate=1,
            tags={'tag': 'tag-value'})

    def test_increment(self):
        self.mock_metrics.emit = mock.MagicMock()
        self.mock_metrics.increment('name', 'value', tag='tag-value')
        self.mock_metrics.emit.assert_called_with(
            'increment',
            metric_name='name',
            value='value',
            sample_rate=1,
            tags={'tag': 'tag-value'})

    def test_decrement(self):
        self.mock_metrics.emit = mock.MagicMock()
        self.mock_metrics.decrement('name', 'value', tag='tag-value')
        self.mock_metrics.emit.assert_called_with(
            'decrement',
            metric_name='name',
            value='value',
            sample_rate=1,
            tags={'tag': 'tag-value'})

    def test_timing(self):
        self.mock_metrics.emit = mock.MagicMock()
        self.mock_metrics.timing('name', 'value', tag='tag-value')
        self.mock_metrics.emit.assert_called_with(
            'timing',
            metric_name='name',
            value='value',
            sample_rate=1,
            tags={'tag': 'tag-value'})

    def test_timed(self):
        t = self.mock_metrics.timed('name', tag='tag-value')
        assert t._mock_new_parent is self.mock_timer_manager
