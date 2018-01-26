import logging

from builder import errors
from builder.metrics import MetricsLogger

public_log = logging.getLogger('public')
metrics = MetricsLogger()


def log_docker_version(client):
    for key, value in client.version().items():
        public_log.info("{}: {}".format(key, value))


def process_stream_line(line):
    value = line['stream']
    if isinstance(value, (str, unicode)):
        public_log.info(value, end="")


def process_error_line(line):
    value = line['error']
    if isinstance(value, (str, unicode)):
        raise errors.HighlandError(value)


def build_image(client, build_path, dockerfile, tag, cache_repo=None):
    public_log.info("Starting build of {}...".format(tag))
    args = dict(
        path=build_path,
        dockerfile=dockerfile,
        tag=tag,
        nocache=not cache_repo,
        decode=True,
        stream=True,
        rm=True,
        pull=True,
        forcerm=True, )
    if cache_repo:
        args['cache_from'] = [cache_repo]
    stream = client.build(**args)

    for line in stream:
        if 'stream' in line:
            process_stream_line(line)
        elif 'error' in line:
            process_error_line(line)


def multitag_image(client, image, repo, tags):
    for tag in tags:
        client.tag(image, repo, tag)


def add_this_tag(client, image):
    # This is for Docker Cloud compatibility, where the built images is called "this"
    client.tag(image, 'this', force=True)
