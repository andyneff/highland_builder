import functools
import logging
import time

private_log = logging.getLogger('private')


class TimedContextManagerDecorator(object):
    """A context manager and a decorator which will report the elapsed time in
    the context OR in a function call.

    ported from:
    https://github.com/DataDog/datadogpy/blob/master/datadog/dogstatsd/base.py

    """

    def __init__(self, metrics_log, metric=None, tags=None, sample_rate=1):
        self.metrics_log = metrics_log
        self.metric = metric
        self.tags = tags
        self.sample_rate = sample_rate
        self.elapsed = None

    def __call__(self, func):
        """
        Decorator which returns the elapsed time of the function call.
        Default to the function name if metric was not provided.
        """
        if not self.metric:
            self.metric = '%s.%s' % (func.__module__, func.__name__)

        # Others
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                self._send(start)

        return wrapped

    def __enter__(self):
        if not self.metric:
            raise TypeError("Cannot used timed without a metric!")
        self.start = time.time()
        return self

    def __exit__(self, type, value, traceback):
        # Report the elapsed time of the context manager.
        self._send(self.start)

    def _send(self, start):
        elapsed = time.time() - start
        self.metrics_log.timing(self.metric, elapsed, self.sample_rate,
                                **self.tags)
        self.elapsed = elapsed

    def start(self):
        self.__enter__()

    def stop(self, **tags):
        self.tags.update(tags)
        self.__exit__(None, None, None)


class MetricsLogger(object):
    def __init__(self):
        self._log = logging.getLogger('metrics')

    def emit(self, method, **kwargs):
        metric_name = "builder_{}".format(kwargs.pop('metric_name'))
        private_log.debug("emitting metric", method=method, **kwargs)
        self._log.info(metric_name, method=method, **kwargs)

    def guage(self, metric_name, value, sample_rate=1, **tags):
        self.emit(
            'guage',
            metric_name=metric_name,
            value=value,
            tags=tags,
            sample_rate=sample_rate)

    def increment(self, metric_name, value=1, sample_rate=1, **tags):
        self.emit(
            'increment',
            metric_name=metric_name,
            value=value,
            tags=tags,
            sample_rate=1)

    def decrement(self, metric_name, value=1, sample_rate=1, **tags):
        self.emit(
            'decrement',
            metric_name=metric_name,
            value=value,
            tags=tags,
            sample_rate=sample_rate)

    def timing(self, metric_name, value, sample_rate=1, **tags):
        self.emit(
            'timing',
            metric_name=metric_name,
            value=value,
            tags=tags,
            sample_rate=sample_rate)

    def timed(self, metric_name, sample_rate=1, **tags):
        return TimedContextManagerDecorator(self, metric_name, tags,
                                            sample_rate)
