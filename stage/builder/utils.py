import errno
import requests
import subprocess
import logging

from builder import errors

public_log = logging.getLogger('public')
private_log = logging.getLogger('private')


def clean_path(path, force_relative=True):
    """
    convert an absolute path to a relative one
    """
    if path.startswith('/'):
        path = path[1:]
    if not path.startswith("./") and force_relative:
        path = "./" + path
    return path


def get_output(command):
    proc = subprocess.Popen(command, stdout=subprocess.PIPE)
    result = proc.communicate()
    return result[0][:-1]


def execute_command(command, error=None):
    """
    run command and raise HighlandError if command fails

    :param command: the command to run
    :param error: a message to include in the raised error
                  if error is callable it is treated as a function
                  that takes in process output and outputs and error
    """
    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1)
    except OSError as oerr:
        if oerr.errno == errno.ENOEXEC:
            errmsg = "Could not execute hook at '{}'. Is it missing a #! line?".format(
                command)
            raise errors.HighlandError(errmsg)
        else:
            raise

    collected_output = ''
    for line in iter(proc.stdout.readline, b''):
        if callable(error):
            collected_output += line
        public_log.info(line.decode("utf-8", "ignore"))
    result = proc.wait()
    if result != 0 and error:
        if callable(error):
            raise errors.HighlandError('{} ({})'.format(
                error(collected_output), result))
        raise errors.HighlandError('{} ({})'.format(error, result))


def clean_log_attr(value):
    if isinstance(value, (str, unicode)):
        return value.encode('utf8', 'replace')
    else:
        return str(value)


def post_to_url(post_spec, file_path, attempts=5):
    if not post_spec:
        return

    for try_index in range(attempts):
        with open(file_path, 'rb') as fd:
            try:
                response = requests.post(
                    post_spec['url'],
                    data=post_spec['fields'],
                    files={'file': fd})
                if response.status_code != 204:
                    private_log.info(
                        "post error",
                        code=response.status_code,
                        text=response.text)
                else:
                    return True
            except:
                private_log.exception(
                    "post failure", file_path=file_path, post_spec=post_spec)
    else:
        raise errors.HighlandError("Could not post to url {}".format(post_spec[
            'url']))


def fetch_from_url(get_url, file_path, attempts=5):
    if not get_url:
        return

    for try_index in range(attempts):
        try:
            r = requests.get(get_url)
            if r.status_code != 200:
                continue

            with open(file_path, 'wb') as fobj:
                for chunk in r:
                    fobj.write(chunk)
            return True
        except Exception:
            msg = "Warning: Exception while downloading {} from {}"
            public_log.info(msg.format(file_path, get_url))
            continue
