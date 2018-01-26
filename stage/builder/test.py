import glob
import logging

from builder import utils, errors

public_log = logging.getLogger('public')
private_log = logging.getLogger('private')


def container_name(build_code):
    return '{}_sut_1'.format(build_code)


def build_test_stack(test_path, build_code):
    cmd = ['docker-compose', '-f', test_path, '-p', build_code, 'build']
    msg = 'building {}'.format(test_path)
    utils.execute_command(cmd, msg)


def boot_test_stack(test_path, build_code):
    cmd = [
        'docker-compose', '-f', test_path, '-p', build_code, 'up', '-d', 'sut'
    ]
    msg = 'starting "sut" service in {}'.format(test_path)
    utils.execute_command(cmd, msg)


def stream_test_output(client, build_code):
    container = container_name(build_code)
    stream = client.logs(container, stream=True)
    for line in stream:
        data = line.decode("utf-8", "ignore")
        public_log.info(data)


def wait_for_test(client, build_code):
    container = container_name(build_code)
    return client.wait(container)


def remove_test_stack(test_path, build_code):
    cmd = [
        'docker-compose', '-f', test_path, '-p', build_code, 'rm', '--force',
        '-v'
    ]
    utils.execute_command(cmd)


def handle_test_result(result, test_path):
    if result:
        msg = 'executing {} ({})'.format(test_path, result)
        raise errors.HighlandError(msg)
    else:
        public_log.info('Tests in {} succeeded'.format(test_path))


def run_test(client, test_path, build_code):
    public_log.info("Starting Test in {}...".format(test_path))
    build_test_stack(test_path, build_code)
    boot_test_stack(test_path, build_code)
    stream_test_output(client, build_code)
    result = wait_for_test(client, build_code)
    remove_test_stack(test_path, build_code)
    handle_test_result(result, test_path)


def test(client, build_code):
    private_log.info("Starting Test")
    for test_path in glob.glob('*[.-]test.yml'):
        run_test(client, test_path, build_code)
