import errno
import os
import glob
import logging
import shutil

import docker
from docker import auth

from builder import errors, utils

public_log = logging.getLogger('public')
private_log = logging.getLogger('private')


def log_build_destination(byon):
    if byon:
        public_log.info("Building in User Node '{}'...".format(byon))
    else:
        public_log.info("Building in Docker Cloud's infrastructure...")


def prepare_build_stage(build_code):
    os.chdir('/src')
    try:
        os.makedirs(build_code)
    except OSError as oerr:
        # in the event of an infrastructure failure the retried build
        # may be scheduled on the same (e.g. BYON) builder -- in this case
        # the old directory should be purged and the build started fresh
        # TODO investigate possible docker bug that causes build container to
        # disappear when running local tests
        if oerr.errno != errno.EEXIST:
            raise
        shutil.rmtree(build_code)
        os.makedirs(build_code)
    os.chdir(build_code)


def dockerfile_for_file_path(build_path, dockerfile_path):
    if dockerfile_path:
        build_path_dir, build_path_file = os.path.split(build_path)
        if build_path_file != dockerfile_path:
            raise errors.HighlandError(
                "Conflicting desired dockerfiles in {}: {}, {}".format(
                    build_path_dir, build_path_file, dockerfile_path))
    build_path, dockerfile_path = os.path.split(build_path)
    return os.path.abspath(build_path), dockerfile_path


def dockerfile_for_dir_path(build_path, dockerfile_path):
    dockerfile_path = dockerfile_path or 'Dockerfile'
    filename = os.path.join(build_path, dockerfile_path)
    if not os.path.isfile(filename):
        if os.path.isdir(filename):
            hint_dockerfile = os.path.join(filename, 'Dockerfile')
            raise errors.HighlandError(
                "Dockerfile location '{}' points to a directory."
                "Perhaps this was supposed to be the build path or "
                "you meant for '{}' to be the dockerfile location."
                .format(filename, hint_dockerfile))
        else:
            raise errors.HighlandError("Dockerfile not found at {}".format(
                filename))
    return os.path.abspath(build_path), dockerfile_path


def resolve_dockerfile_path(build_path, dockerfile_path):
    """
    Return the real Dockerfile name.
    """
    dockerfile_path = utils.clean_path(dockerfile_path, False)

    if os.path.isfile(build_path):
        return dockerfile_for_file_path(build_path, dockerfile_path)
    elif os.path.isdir(build_path):
        return dockerfile_for_dir_path(build_path, dockerfile_path)
    else:
        raise errors.HighlandError("Build path does not exist: {}".format(
            build_path))


def resolve_readme_path(build_path, dockerfile_folder):
    """
    Print out the README file so it can be read by the agent
    """
    private_log.info("Getting README")
    candidate_dirs = [build_path, dockerfile_folder, "."]
    candidate_globs = ['README.md', '[Rr][Ee][Aa][Dd][Mm][Ee]*']

    for candidate_dir in candidate_dirs:
        for candidate_glob in candidate_globs:
            fileglob = os.path.join(candidate_dir, candidate_glob)
            candidates = glob.glob(fileglob)
            if candidates:
                return candidates[0]  # TODO is one better than the others?


def snapshot_tags(client):
    images = client.images()
    return set().union(*(image.get('RepoTags') or [] for image in images))


def snapshot_containers(client):
    return set(container.get('Id') for container in client.containers())


def write_docker_cfg(dockercfg, path="/root/.dockercfg"):
    with open(path, 'w') as config_file:
        config_file.write(dockercfg)


def login(docker_host, dockercfg=None):
    if dockercfg:
        write_docker_cfg(dockercfg)
    # HACK should get timeout parametrically
    client = docker.client.APIClient(
        docker_host, version='auto', timeout=60 * 120)
    client._auth_configs = auth.load_config('/root/.dockercfg')
    return client
