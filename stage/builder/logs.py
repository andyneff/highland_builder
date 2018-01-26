import logging
import logging.config

from pythonjsonlogger import jsonlogger


def getRootHandler():
    return {'class': 'logging.NullHandler'}


def getStandardHandler():
    '''Returns a handler config for logging to standard output

    This handler is for emitting the content of the public log to
    stdout so it can be viewed in normal circumstances like when
    viewing the output of the container.
    '''
    config = {
        'class': 'logging.StreamHandler',
        'stream': 'ext://sys.stdout',
    }
    return config


def getPublicHandler(filename='/public.log',
                     max_size=int(64e6),
                     structured=False):
    '''Returns a handler config for emission to the public log file

    This handler controls the logfile that the public will actually
    see.'''

    config = {
        'class': 'builder.logs.MaxBytesHandler',
        'filename': filename,
        'maxBytes': max_size,
    }

    if structured:
        config['formatter'] = 'structured'
    return config


def getPrivateHandler(filename='/private.log'):
    '''Returns a handler config for emission to the private log file

    This handler recieves all typical logging emissions and writes them
    to the private log which is never seen by the public. It uses the
    `structured` formatter and emits structured json records. These will
    always include the cluster_name.
    '''
    return {
        'class': 'logging.FileHandler',
        'filename': filename,
        'formatter': 'structured',
    }


def getMetricsHandler(filename='/metrics.log'):
    '''Returns a handler config for emission to the metrics log file

    This handler recieves all typical logging emissions and writes them
    to the metrics log which is processed by agents. It uses the
    `json` formatter and emits structured json records.
    '''
    return {
        'class': 'logging.FileHandler',
        'filename': filename,
        'formatter': 'json',
    }


def getHandlers(structured=False):
    '''Returns a dictionary of standard-logging handlers'''
    return {
        # nullary root handler
        'root': getRootHandler(),
        # unstructured stdout logger
        'standard': getStandardHandler(),
        # structured file loggers
        'public': getPublicHandler(structured=structured),
        'private': getPrivateHandler(),
        'metrics': getMetricsHandler(),
    }


def getFormatters(cluster_name):
    '''Returns a dictionary of logging formatters'''
    return {
        'structured': {
            '()': 'builder.logs.BuilderJsonFormatter',
            'cluster_name': cluster_name,
        },
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
        }
    }


def getLoggers(private_level=logging.DEBUG):
    '''Returns a dictionary containing top-level logging configuration'''
    return {
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
            'level': private_level
        },
        'metrics': {
            'handlers': ['metrics'],
            'level': logging.DEBUG
        },
    }


def getConfig(cluster_name, structured=False):
    handlers = getHandlers(structured=structured)
    formatters = getFormatters(cluster_name)
    loggers = getLoggers()
    return dict(
        version=1,
        disable_existing_loggers=True,
        formatters=formatters,
        handlers=handlers,
        loggers=loggers)


class BuilderLogger(logging.Logger):
    reserved_keys = ("message", "asctime")

    def __init__(self, *args, **kwargs):
        self.step = kwargs.pop('step', None)
        super(BuilderLogger, self).__init__(*args, **kwargs)

    def makeRecord(self,
                   name,
                   level,
                   fn,
                   lno,
                   msg,
                   args,
                   exc_info,
                   func=None,
                   extra=None):
        rv = logging.LogRecord(name, level, fn, lno, msg, args, exc_info, func)
        if extra is not None:
            for key in extra:
                if (key in self.reserved_keys) or (key in rv.__dict__):
                    new_key = "data_{}".format(key)
                    rv.__dict__[new_key] = extra[key]
                else:
                    rv.__dict__[key] = extra[key]
        return rv

    def _log(self, level, msg, args, exc_info=None, extra=None, **kwargs):
        if extra is None:
            extra = {}

        if kwargs:
            extra.update(kwargs)

        if 'step' not in extra and self.step is not None:
            extra['step'] = self.step

        return super(BuilderLogger, self)._log(level, msg, args, exc_info,
                                               extra)


class MaxBytesHandler(logging.handlers.RotatingFileHandler):
    def __init__(self,
                 filename,
                 mode='a',
                 maxBytes=0,
                 encoding=None,
                 delay=False,
                 truncated_msg="<Max Log-size Reached>"):
        super(MaxBytesHandler, self).__init__(
            filename, mode, maxBytes, encoding=encoding, delay=delay)
        self.full = False
        self.truncated_msg = truncated_msg

    def emit(self, record):
        """
        Emit a record.
        Output the record to the file, catering for rollover as described
        in doRollover().
        """
        if self.full:
            return

        try:
            if self.shouldRollover(record):
                self.full = True
                record.msg = self.truncated_msg
            logging.FileHandler.emit(self, record)
        except Exception:
            self.handleError(record)


class BuilderJsonFormatter(jsonlogger.JsonFormatter):
    """
    Implements the standard Docker JSON format and parsed by our
    centralized logging infrastructure.
    """

    def __init__(self, *args, **kwargs):
        self.cluster_name = kwargs.pop('cluster_name', None)
        super(BuilderJsonFormatter, self).__init__(*args, **kwargs)

    def process_log_record(self, log_record):
        """
        Add keys to the log recorded that will added to the json object

        TODO: We should include the deployment version
        """
        # We expect that all hub projects will follow this convention.
        log_record['cluster_name'] = self.cluster_name
        return log_record


def initializeLogger(cluster_name, structured=False):
    logging.setLoggerClass(BuilderLogger)
    logging.config.dictConfig(
        getConfig(
            cluster_name, structured=structured).items())
