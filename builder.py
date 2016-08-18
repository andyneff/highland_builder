#!/usr/bin/env python
"""
This is the build script for the DockerHub automated build service. It executes
inside of a container on some Docker host and is invoked by some remote Agent.

Details of the build are provided by the environment and the output is
streamed back to the Agent. The build process involves cloning the build
context from some version control repository, building the configured
Dockerfile and pushing the resulting image back to the registry.

The entire build host is destroyed after job completion or failure so no
subsequent cleanup is required.
"""
from __future__ import print_function

import codecs
import functools
import glob
import json
import os
import requests
import shutil
import signal
import subprocess
import tempfile
import time
import traceback

from docker import Client
from docker.auth import auth

logger = None
# unique identifier for build job
BUILD_CODE = os.environ['BUILD_CODE']
# ssh private key for private source repos
SSH_PRIVATE = os.environ.get('SSH_PRIVATE')
# the kind of version control repository
SOURCE_TYPE = os.environ['SOURCE_TYPE']
# the url of the version control repository
SOURCE_URL = os.environ['SOURCE_URL']
# the branch of the repository to build
SOURCE_BRANCH = os.environ.get('SOURCE_BRANCH')
# the commit of the repository to build
SOURCE_COMMIT = os.environ.get('SOURCE_COMMIT')
# the Docker repository tag to push to
DOCKER_REPO = os.environ['DOCKER_REPO']
# the tag for the built image
DOCKER_TAG = os.environ.get('DOCKER_TAG', 'latest').replace(" ", "")
DOCKER_TAGS = DOCKER_TAG.split(",")
# if the built image is pushed
PUSH = os.environ.get('PUSH').upper()
# the docker host to execute the build against
DOCKER_HOST = os.environ['DOCKER_HOST']
# the hostname of the byon that does the build
BYON = os.environ.get('BYON')

DOCKERCFG = os.environ['DOCKERCFG']
BUILD_PATH = os.environ.get('BUILD_PATH', '/')
DOCKERFILE_PATH = os.environ.get('DOCKERFILE_PATH', '')

LOGS_POST_SPEC = json.loads(os.environ['LOGS_POST_SPEC'])
README_POST_SPEC = json.loads(os.environ['README_POST_SPEC'])
DOCKERFILE_POST_SPEC = json.loads(os.environ['DOCKERFILE_POST_SPEC'])
MAX_LOG_SIZE = int(os.environ['MAX_LOG_SIZE'])

LOGIN_EMAIL = "highland@docker.com"
PUSH_ATTEMPT_COUNT = 5
GIT_PATH = '/usr/bin/git'

# if the repository is a private github repository
# ensure that we are using the ssh form of the git url
if SSH_PRIVATE and SOURCE_URL.startswith("https://github.com"):
    SOURCE_URL = SOURCE_URL.replace("https://", "git@", 1)
    SOURCE_URL = SOURCE_URL.replace("/", ":", 1)

# Env vars for Docker Cloud compatibility
IMAGE_NAME = '{}:{}'.format(DOCKER_REPO, DOCKER_TAGS[0])
os.environ["IMAGE_NAME"] = IMAGE_NAME

# outputs from git to denote what failure occured
ACCESS_RIGHTS_SUBSTR = 'Please make sure you have the correct access rights'
NO_BRANCH_SUBSTR = 'not found in'


class BuildLogger(object):
    # build stages for which agent should collect output
    logged_stages = ('info', 'clone', 'cloned', 'build', 'push', 'error',
                     'test')
    truncation_message = "...<Logs Truncated>"

    def __init__(self, logfile):
        self.logfile = logfile
        self.written_bytes = 0
        self.done = False

    def __getattr__(self, attr_name):
        return functools.partial(self.log, attr_name)

    def write_to_logfile(self, message):
        if self.done:
            return
        self.logfile.write(message)
        self.written_bytes += len(message)
        if self.written_bytes > MAX_LOG_SIZE:
            self.logfile.seek(MAX_LOG_SIZE - self.written_bytes, 1)
            self.logfile.seek(-len(self.truncation_message), 1)
            self.logfile.write(self.truncation_message)
            self.logfile.truncate()
            self.done = True

    def log(self, stage, message, end="\n"):
        message = message.encode("utf-8", 'ignore')
        if not message.endswith(end):
            message += end
        if stage in self.logged_stages:
            self.write_to_logfile(message)
        print(message, end="")


class HighlandError(Exception):
    pass


def post_to_url(post_spec, file_path):
    if not post_spec:
        return

    for try_index in range(PUSH_ATTEMPT_COUNT):
        try:
            with codecs.open(file_path,
                             'rb',
                             encoding="utf-8",
                             errors="ignore") as fd:
                response = requests.post(post_spec['url'],
                                         data=post_spec['fields'],
                                         files={'file': fd})
            assert response.status_code == 204
            break
        except Exception:
            continue
    else:
        raise HighlandError("Could not post to url")


def clean_log_attr(value):
    if isinstance(value, (str, unicode)):
        return value.encode('utf8', 'replace')
    else:
        return str(value)


def execute_command(stage, command, error=None):
    """
    run command and raise HighlandError if command fails

    :param stage: the stage to pass into the logger
    :param command: the command to run
    :param error: a message to include in the raised error
                  if error is callable it is treated as a function
                  that takes in process output and outputs and error
    """
    proc = subprocess.Popen(command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            bufsize=1)
    collected_output = ''
    for line in iter(proc.stdout.readline, b''):
        if callable(error):
            collected_output += line
        getattr(logger, stage)(line.decode("utf-8", "ignore"))
    result = proc.wait()
    if result != 0 and error:
        if callable(error):
            raise HighlandError('{} ({})'.format(
                error(collected_output), result))
        raise HighlandError('{} ({})'.format(error, result))


def get_output(command):
    return subprocess.Popen(command,
                            stdout=subprocess.PIPE).communicate()[0][:-1]


def write_private_key():
    private_key_path = os.path.expanduser("~/.ssh/id_rsa")
    with open(private_key_path, 'w') as fd:
        fd.write(SSH_PRIVATE)
        fd.write('\n')
    os.chmod(private_key_path, 0600)


def get_clone_commands():
    """
    Return a list of command parts suitable for Popen that will
    clone the source of the build context
    """
    if SOURCE_TYPE == 'git':
        if SOURCE_COMMIT:
            return [
                [GIT_PATH, 'clone', '--recursive', SOURCE_URL, '.'],
                [GIT_PATH, 'checkout', '-B', SOURCE_BRANCH or "master",
                 SOURCE_COMMIT],
                [GIT_PATH, 'submodule', 'update'],
            ]
        else:
            return [
                [GIT_PATH, 'clone', '--recursive', '--depth', '1', '-b',
                 SOURCE_BRANCH or "master", SOURCE_URL, '.'],
                [GIT_PATH, 'submodule', 'update'],
            ]

    elif SOURCE_TYPE == 'hg':
        return [
            ['/usr/bin/hg', 'clone', '-r', SOURCE_BRANCH or "default",
             SOURCE_URL, '.']
        ]

    else:
        raise HighlandError("Invalid SCM type: %r must be git or hg" %
                            SOURCE_TYPE)


def convert_clone_error(clone_error):
    if ACCESS_RIGHTS_SUBSTR in clone_error:
        return (
            'please ensure the correct public key is added to the list of trusted '
            'keys for this repository')
    if NO_BRANCH_SUBSTR in clone_error:
        return 'please ensure the remote branch exists'

    return (
        'please ensure the correct public key is added to the list of trusted '
        'keys for this repository and the remote branch exists.')


def clone():
    """
    Clone the source of the build context and set it as the working directory
    """
    logger.clone("Starting to clone")
    if SSH_PRIVATE:
        write_private_key()
    clone_commands = get_clone_commands()
    for clone_command in clone_commands:
        execute_command('clone', clone_command, convert_clone_error)
    if SOURCE_TYPE == 'git':
        os.environ['GIT_SHA1'] = get_output(['git', 'rev-parse', 'HEAD'])
        os.environ['GIT_MSG'] = get_output(['git', 'log', '--format=%B', '-n',
                                            '1', os.environ['GIT_SHA1']])
        os.environ['COMMIT_MSG'] = os.environ['GIT_MSG']
    del os.environ['SOURCE_URL']
    logger.clone("Cloning done")


def clean_path(path, ensure_start=True):
    """
    convert an absolute path to a relative one
    """
    if path.startswith('/'):
        path = path[1:]
    if not path.startswith("./") and ensure_start:
        path = "./" + path
    return path


def get_build_params(build_path, dockerfile_path):
    """
    Return the real build path and Dockerfile name.
    """
    build_path = clean_path(build_path)
    dockerfile_path = clean_path(dockerfile_path, False)

    if os.path.isfile(build_path):
        if dockerfile_path:
            build_path_dir, build_path_file = os.path.split(build_path)
            if build_path_file != dockerfile_path:
                raise HighlandError(
                    "Conflicting desired dockerfiles in {}: {}, {}".format(
                        build_path_dir, build_path_file, dockerfile_path))
        build_path, dockerfile_path = os.path.split(build_path)
    elif os.path.isdir(build_path):
        dockerfile_path = dockerfile_path or 'Dockerfile'
        if not os.path.isfile(os.path.join(build_path, dockerfile_path)):
            raise HighlandError("Dockerfile not found at {}".format(
                os.path.join(build_path, dockerfile_path)))
    else:
        raise HighlandError("Build path does not exist: {}".format(build_path))

    return build_path, dockerfile_path


def print_dockerfile(raw_build_path, raw_dockerfile_path):
    """
    Print out the Dockerfile so it can be read by the agent
    """
    logger.dockerfile("Getting Dockerfile")
    build_path, dockerfile_path = get_build_params(raw_build_path,
                                                   raw_dockerfile_path)
    post_to_url(DOCKERFILE_POST_SPEC, os.path.join(build_path,
                                                   dockerfile_path))
    return build_path, dockerfile_path


def get_readme(build_path):
    """
    Print out the README file so it can be read by the agent
    """
    logger.readme("Getting README")
    candidate_dirs = [build_path, "."]
    candidate_globs = ['README.md', '[Rr][Ee][Aa][Dd][Mm][Ee]*']
    readme_path = None

    for candidate_dir in candidate_dirs:
        for candidate_glob in candidate_globs:
            fileglob = os.path.join(candidate_dir, candidate_glob)
            candidates = glob.glob(fileglob)
            if candidates:
                return candidates[0]  # TODO is one better than the others?


def write_docker_cfg():
    if DOCKERCFG:
        with open("/root/.dockercfg", 'w') as config_file:
            config_file.write(DOCKERCFG)


def login():
    # HACK should get timeout parametrically
    client = Client(DOCKER_HOST, version='auto', timeout=60 * 120)
    client._auth_configs = auth.load_config('/root/.dockercfg')
    return client


def build(client, dockerfile_path):
    logger.build("Starting Build")

    if os.path.isfile('hooks/pre_build'):
        logger.build('Executing pre_build hook...')
        execute_command('build', 'hooks/pre_build', 'pre_build hook failed!')

    if os.path.isfile('hooks/build'):
        logger.build('Executing build hook...')
        execute_command('build', 'hooks/build', 'build hook failed!')
    else:
        for key, value in client.version().items():
            logger.build("{}: {}".format(key, value))
        logger.build("Starting build of {}...".format(IMAGE_NAME))
        for line in client.build(path='.',
                                 dockerfile=dockerfile_path,
                                 tag=IMAGE_NAME,
                                 nocache=True,
                                 decode=True,
                                 stream=True,
                                 rm=True,
                                 forcerm=True):

            if isinstance(line.get('stream'), (str, unicode)):
                logger.build(line.get('stream'), end="")

            if isinstance(line.get('error'), (str, unicode)):
                raise HighlandError(line.get('error', ""))

        for alias_tag in DOCKER_TAGS[1:]:
            client.tag(IMAGE_NAME, DOCKER_REPO, alias_tag)

        #This is for Docker Cloud compatibility, where the built images is called "this"
        client.tag(IMAGE_NAME, 'this', force=True)

    if os.path.isfile('hooks/post_build'):
        logger.build('Executing post_build hook...')
        execute_command('build', 'hooks/post_build', 'post_build hook failed!')


def test(client):
    logger.test("Starting Test")

    if os.path.isfile('hooks/pre_test'):
        logger.test('Executing pre_test hook...')
        execute_command('test', 'hooks/pre_test', 'pre_test hook failed!')

    if os.path.isfile('hooks/test'):
        logger.test('Executing test hook...')
        execute_command('test', 'hooks/test', 'test hook failed!')
    else:
        for test_path in glob.glob('*[.-]test.yml'):
            logger.test("Starting Test in {}...".format(test_path))
            execute_command('test',
                            ['docker-compose', '-f', test_path, 'pull'])
            execute_command(
                'test',
                ['docker-compose', '-f', test_path, '-p', BUILD_CODE, 'build'],
                'building {}'.format(test_path))
            execute_command('test', ['docker-compose', '-f', test_path, '-p',
                                     BUILD_CODE, 'up', '-d', 'sut'],
                            'starting "sut" service in  {}'.format(test_path))
            for line in client.logs('{}_sut_1'.format(BUILD_CODE),
                                    stream=True):
                logger.test(line.decode("utf-8", "ignore"))

            result = client.wait('{}_sut_1'.format(BUILD_CODE))

            execute_command('test', ['docker-compose', '-f', test_path, '-p',
                                     BUILD_CODE, 'rm', '--force', '-v'])

            if result:
                raise HighlandError('executing {} ({})'.format(test_path,
                                                               result))
            else:
                logger.test('Tests in {} succeeded'.format(test_path))

    if os.path.isfile('hooks/post_test'):
        logger.test('Executing post_test hook...')
        execute_command('test', 'hooks/post_test', 'post_test hook failed!')


def format_push_line(push_line_encoded):
    push_line = json.loads(push_line_encoded)

    if push_line.get('status') == 'Pushing':
        details = push_line.get('progressDetail')
        return "{} Pushing: {} {}/{}".format(
            push_line.get('id'), push_line.get('progress'),
            *map(details.get, ['current', 'total']))

    if push_line.get('status') in ['Waiting', 'Preparing', 'Pushed']:
        return "{}: {}".format(push_line.get('id'), push_line['status'])

    if push_line.keys() == ['status']:
        return push_line['status']

    if set(push_line.keys()) == {'progressDetail', 'aux'} \
       and not push_line['progressDetail'] and isinstance(push_line['aux'], dict):
        return "\n".join("  {}: {}".format(key, value)
                         for key, value in push_line['aux'].items())

    return push_line_encoded


def push(client):
    if PUSH == 'TRUE':
        logger.push("Starting Push")

        if os.path.isfile('hooks/pre_push'):
            logger.push('Executing pre_push hook...')
            execute_command('push', 'hooks/pre_push', 'pre_push hook failed!')

        if os.path.isfile('hooks/push'):
            logger.push('Executing push hook...')
            execute_command('push', 'hooks/push', 'push hook failed!')
        else:
            logger.push("Starting push of {}".format(IMAGE_NAME))
            for try_index in range(PUSH_ATTEMPT_COUNT):
                error = None
                if try_index > 0:
                    logger.push("Push failed. Attempt %i in 60 seconds." %
                                (try_index + 1))
                    time.sleep(60)
                for tag in DOCKER_TAGS:
                    for line in client.push(DOCKER_REPO, tag=tag, stream=True):
                        try:
                            logger.push(format_push_line(line))
                        except Exception:
                            logger.push(line)
                        line_parsed = json.loads(line)
                        if "errorDetail" in line_parsed:
                            error = line_parsed.get("errorDetail") or ""
                        if "error" in line_parsed:
                            error = line_parsed.get("error") or ""
                    if error is not None:
                        break
                if error is None:
                    break
            else:
                raise HighlandError(error or "Error pushing tags")

        if os.path.isfile('hooks/post_push'):
            logger.push('Executing post_push hook...')
            execute_command('push', 'hooks/post_push',
                            'post_push hook failed!')


def cleanup(client, original_tags, original_containers):
    if os.path.isdir(BUILD_CODE):
        shutil.rmtree(BUILD_CODE)

    if original_containers is not None:
        current_containers = set(container.get('Id')
                                 for container in client.containers())
        new_containers = current_containers - original_containers
        for container in sorted(new_containers):
            try:
                client.remove_container(container, force=True)
            except Exception:
                logger.cleanup("Could not remove container: {}".format(
                    container))

    if original_tags is not None:
        current_tags = set().union(*(image.get('RepoTags')
                                     for image in client.images()))
        new_tags = current_tags - original_tags
        for tag in sorted(new_tags):
            try:
                client.remove_image(tag, force=True)
            except Exception:
                logger.cleanup("Could not remove image: {}".format(tag))


def run():
    client = None
    original_tags = None
    original_containers = None
    try:
        if BYON:
            logger.info("Building in User Node '{}'...".format(BYON))
        else:
            logger.info("Building in Docker Cloud's infrastructure...")

        os.chdir('/src')
        os.makedirs(BUILD_CODE)
        os.chdir(BUILD_CODE)
        clone()
        build_path, dockerfile_path = print_dockerfile(BUILD_PATH,
                                                       DOCKERFILE_PATH)
        readme_path = get_readme(build_path)
        if readme_path:
            post_to_url(README_POST_SPEC, readme_path)
        os.chdir(build_path)

        if os.path.isdir('hooks'):
            subprocess.call(['chmod', '-R', '+x', 'hooks'])

        if os.path.isfile('hooks/post_checkout'):
            logger.clone('Executing post_checkout hook...')
            execute_command('clone', 'hooks/post_checkout',
                            'post_checkout hook failed!')

        write_docker_cfg()
        client = login()
        original_tags = set().union(*(image.get('RepoTags')
                                      for image in client.images()))
        original_containers = set(container.get('Id')
                                  for container in client.containers())

        build(client, dockerfile_path)
        test(client)
        push(client)
        logger.finished("Build finished")
    except HighlandError as exc:
        logger.error(str(exc))
        return 2
    except Exception as exc:
        logger.error('Unexpected error')
        logger.main('Encountered error: {}\n{}'.format(exc,
                                                       traceback.format_exc()))
        return 1
    finally:
        try:
            if client:
                cleanup(client, original_tags, original_containers)
        except Exception as exc:
            logger.error('Unexpected error while cleaning up')
            logger.main('Unexpected error while cleaning up: {}\n{}'.format(
                exc, traceback.format_exc()))


def interrupt_handler(signum, frame):
    logger.error('Build canceled.')
    post_to_url(LOGS_POST_SPEC, logger.logfile.name)
    exit(3)


def main():
    global logger
    signal.signal(signal.SIGTERM, interrupt_handler)
    with tempfile.NamedTemporaryFile(delete=False) as logfile:
        logger = BuildLogger(logfile)
        exit_code = run()
    post_to_url(LOGS_POST_SPEC, logfile.name)
    exit(exit_code)


if __name__ == "__main__":
    main()
