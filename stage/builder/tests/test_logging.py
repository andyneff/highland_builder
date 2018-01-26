import logging

from builder import logs
from builder.tests.utils import PatchCase


def test_getRootHandler():
    handler = logs.getRootHandler()
    assert handler == {'class': 'logging.NullHandler', }


class GetStandardHandlerCase(PatchCase):
    def test_defaults(self):
        handler = logs.getStandardHandler()
        assert handler == {
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
        }

    def test_structured(self):
        handler = logs.getStandardHandler()
        assert handler == {
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
        }


class GetPublicHandlerCase(PatchCase):
    def test_defaults(self):
        handler = logs.getPublicHandler()
        assert handler == {
            'class': 'builder.logs.MaxBytesHandler',
            'filename': '/public.log',
            'maxBytes': 64e6,
        }

    def test_args(self):
        handler = logs.getPublicHandler('foo', 0)
        assert handler == {
            'class': 'builder.logs.MaxBytesHandler',
            'filename': 'foo',
            'maxBytes': 0,
        }


class GetPrivateHandlerCase(PatchCase):
    def test_defaults(self):
        handler = logs.getPrivateHandler()
        assert handler == {
            'class': 'logging.FileHandler',
            'filename': '/private.log',
            'formatter': 'structured',
        }

    def test_args(self):
        handler = logs.getPrivateHandler('foo')
        assert handler == {
            'class': 'logging.FileHandler',
            'filename': 'foo',
            'formatter': 'structured',
        }


class GetHandlersCase(PatchCase):
    mocks = {
        'root': 'builder.logs.getRootHandler',
        'standard': 'builder.logs.getStandardHandler',
        'public': 'builder.logs.getPublicHandler',
        'private': 'builder.logs.getPrivateHandler',
    }

    def test_calls(self):
        handlers = logs.getHandlers()
        assert handlers['root']._mock_new_parent == self.mock_root
        assert handlers['standard']._mock_new_parent == self.mock_standard
        assert handlers['public']._mock_new_parent == self.mock_public
        assert handlers['private']._mock_new_parent == self.mock_private


class GetFormattersCase(PatchCase):
    def test_args(self):
        formatters = logs.getFormatters('foo')
        assert formatters == {
            'structured': {
                '()': 'builder.logs.BuilderJsonFormatter',
                'cluster_name': 'foo',
            },
            'json': {
                '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            }
        }


class GetLoggersCase(PatchCase):
    def test_result(self):
        loggers = logs.getLoggers()
        assert loggers == {
            '': {
                'handlers': ['root'],
                'level': logging.NOTSET
            },
            'public': {
                'handlers': ['standard', 'public'],
                'level': logging.INFO
            },
            'private': {
                'handlers': ['private'],
                'level': logging.DEBUG
            },
            'metrics': {
                'handlers': ['metrics'],
                'level': logging.DEBUG
            },
        }


class GetConfigCase(PatchCase):
    mocks = {
        'handlers': 'builder.logs.getHandlers',
        'formatters': 'builder.logs.getFormatters',
        'loggers': 'builder.logs.getLoggers'
    }

    def test_result(self):
        config = logs.getConfig('foo')
        self.mock_formatters.assert_called_with('foo')
        assert config['version'] == 1
        assert config['disable_existing_loggers'] is True
        assert config['formatters']._mock_new_parent == self.mock_formatters
        assert config['handlers']._mock_new_parent == self.mock_handlers
        assert config['loggers']._mock_new_parent == self.mock_loggers


class BuilderLoggerCase(PatchCase):
    mocks = {'record': 'logging.LogRecord', 'logger': 'logging.Logger._log'}

    def mockUp(self):
        self.log = logs.BuilderLogger('name', 1)

    def test_defaults(self):
        assert self.log.reserved_keys == ('message', 'asctime')
        assert self.log.step is None

    def test_initial_step(self):
        self.log = logs.BuilderLogger('name', 1, step='foo')
        assert self.log.step == 'foo'

    def test_make_record(self):
        rv = self.log.makeRecord('name', 'level', 'fn', 'lno', 'msg', 'args',
                                 'exec_info')
        assert rv._mock_new_parent == self.mock_record

    def test_make_record_extras(self):
        rv = self.log.makeRecord(
            'name',
            'level',
            'fn',
            'lno',
            'msg',
            'args',
            'exec_info',
            extra={'foo': 'bar'})
        assert rv.foo == 'bar'

    def test_make_record_reserved_keys(self):
        rv = self.log.makeRecord(
            'name',
            'level',
            'fn',
            'lno',
            'msg',
            'args',
            'exec_info',
            extra={'message': 'bar'})
        assert rv.data_message == 'bar'
