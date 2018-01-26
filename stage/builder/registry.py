import json
import time
import logging

from builder import errors
from builder.metrics import MetricsLogger

public_log = logging.getLogger('public')
private_log = logging.getLogger('private')
metrics = MetricsLogger()


def handle_progress(push_line):
    details = push_line.get('progressDetail')
    return "{} Pushing: {} {}/{}".format(
        push_line.get('id'),
        push_line.get('progress'), *map(details.get, ['current', 'total']))


def handle_id(push_line):
    return "{}: {}".format(push_line.get('id'), push_line['status'])


def handle_status(push_line):
    push_status = push_line.get('status')
    delegates = {
        'Pushing': handle_progress,
        'Waiting': handle_id,
        'Preparing': handle_id,
        'Pushed': handle_id,
    }
    if push_status in delegates:
        delegate = delegates[push_status]
        return delegate(push_line)


def handle_raw_status(push_line):
    if push_line.keys() == ['status']:
        return push_line['status']


def handle_aux_progress(push_line):
    if set(push_line.keys()) == {'progressDetail', 'aux'} \
       and not push_line['progressDetail'] and isinstance(push_line['aux'], dict):
        return "\n".join("  {}: {}".format(key, value)
                         for key, value in push_line['aux'].items())


def format_stream_line(encoded_line):
    stream_line = json.loads(encoded_line)
    status_result = handle_status(stream_line)
    raw_status_result = handle_raw_status(stream_line)
    aux_result = handle_aux_progress(stream_line)
    return status_result or raw_status_result or aux_result or encoded_line


def log_stream_line(line):
    try:
        private_log.info(format_stream_line(line))
    except Exception:
        private_log.info(line)


def registry_operation(operation, repo, tag):
    for line in operation(repo, tag=tag, stream=True):
        log_stream_line(line)
        line_parsed = json.loads(line)
        if "errorDetail" in line_parsed:
            return line_parsed.get("errorDetail") or ""
        if "error" in line_parsed:
            return line_parsed.get("error") or ""


def try_push(client, repo, tags):
    error = None
    for tag in tags:
        error = registry_operation(client.push, repo, tag)
        if error:
            return error


def retry_delay(try_index):
    if try_index > 0:
        public_log.info("Push failed. Attempt %i in 60 seconds." %
                        (try_index + 1))
        time.sleep(60)


def push(client, repo, tags, retry_count=5):
    error = None
    for try_index in range(retry_count):
        retry_delay(try_index)  # delay between retries
        error = try_push(client, repo, tags)
        if error is None:
            break  # no error? let's get out of here
    else:
        # all retries were extinguished
        raise errors.HighlandError(error or "Error pushing tags")


def pull(client, repo, tag, retry_count=5):
    error = None
    for try_index in range(retry_count):
        retry_delay(try_index)  # delay between retries
        error = registry_operation(client.pull, repo, tag)
        if error is None:
            break  # no error? let's get out of here
    else:
        metrics.increment('cache.pull_failure', error=error)
        public_log.info("Error pulling cache tag: {}".format(error))
