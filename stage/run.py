#!/usr/bin/python
import os
import time
import signal
import functools
import logging

from builder.logs import initializeLogger
initializeLogger(
    os.environ.get('CLUSTER_NAME', None), os.environ.get('JSON_LOGGING', None))

public_log = logging.getLogger('public')
public_log.step = "build"

from builder import utils, runner


def interrupt(log_spec, signum, frame):
    public_log.info('Build canceled.')
    utils.post_to_url(log_spec, '/public.log')
    utils.post_to_url(log_spec, '/private.log')
    exit(3)


def install_handler(builder_inst, handler):
    logs_post_spec = builder_inst.signed_urls['post']['logs']
    handler = functools.partial(interrupt, logs_post_spec)
    signal.signal(signal.SIGTERM, handler)


def main():
    build_runner = runner.BuildRunner()
    install_handler(build_runner, interrupt)
    return build_runner.run()


if __name__ == "__main__":
    if os.path.isfile("/completed"):
        while True:
            time.sleep(9999)
    else:
        exit_code = 0
        try:
            exit_code = main()
        except SystemExit as e:
            exit_code = e.code
        finally:
            with open("/completed", 'w') as fobj:
                fobj.write("finished!")
            exit(exit_code)
