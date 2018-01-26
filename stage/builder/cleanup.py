import os
import shutil
import logging

private_log = logging.getLogger('private')


def remove_build_stage(build_code):
    if os.path.isdir(build_code):
        shutil.rmtree(build_code)


def remove_build_containers(client, originals):
    if originals is None:
        return

    current = set(c.get('Id') for c in client.containers())
    introduced = sorted(current - originals)
    for container in introduced:
        try:
            client.remove_container(container, force=True)
        except Exception:
            private_log.info("Could not remove container: {}".format(
                container))


def remove_build_tags(client, originals):
    if originals is None:
        return
    current = set().union(*(i.get('RepoTags') or [] for i in client.images()))
    introduced = sorted(current - originals)
    for tag in introduced:
        try:
            client.remove_image(tag, force=True)
        except Exception:
            private_log.info("Could not remove image: {}".format(tag))
