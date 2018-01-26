#!/usr/bin/env python

from __future__ import print_function

import json
import os
import traceback
import logging

from builder import (vcs, hooks, errors, utils, startup, build, test, registry,
                     cleanup)
from builder.metrics import MetricsLogger

public_log = logging.getLogger('public')
private_log = logging.getLogger('private')
metrics = MetricsLogger()


class BuildRunner(object):
    def __init__(self, environment=None):
        self.client = None
        self.gather_environment(environment or os.environ)
        self.compute_image_name()
        self.compute_cache_name()

    def gather_environment(self, env):
        # build details

        # unique identifier for build job
        self.build_code = env['BUILD_CODE']
        # the Docker repository tag to push to
        self.docker_repo = env['DOCKER_REPO']
        # the tag for the built image
        self.docker_tags = env.get('DOCKER_TAG', 'latest').split(',')
        self.docker_tag = self.docker_tags[0]

        # source repository details

        # the kind of version control repository
        self.source_type = env['SOURCE_TYPE']
        # the url of the version control repository
        self.source_url = env['SOURCE_URL']
        # the branch of the repository to build
        self.source_branch = env.get('SOURCE_BRANCH')
        # the commit of the repository to build
        self.source_commit = env.get('SOURCE_COMMIT')
        # ssh private key for private source repos
        self.ssh_private = env.get('SSH_PRIVATE')
        # where in the repository to root the build context
        self.build_path = env.get('BUILD_PATH', '/')
        # where in the repository the dockerfile is
        self.dockerfile_path = env.get('DOCKERFILE_PATH', '')
        # where in the repository the hooks are
        self.dockerfile_folder = None

        # docker client settings

        # the docker host to execute the build against
        self.docker_host = env['DOCKER_HOST']
        # the docker client configuration
        self.dockercfg = env['DOCKERCFG']

        # builder settings

        # the tag to use for pulling cache if any
        self.cache_tag = env['CACHE_TAG']
        # signed url data
        self.signed_urls = json.loads(env['SIGNED_URLS'])
        # the hostname of the byon that does the build, if any
        self.byon = env.get('BYON')
        # whether the built image is pushed
        self.should_push = str(env.get('PUSH')).upper() == 'TRUE'
        # how many times to retry pushing
        self.push_attempt_count = int(env.get('PUSH_ATTEMPT_COUNT', 5))
        # whether the various build-steps should be logged or not
        self.log_build_steps = env.get('LOG_BUILD_STEPS',
                                       'False').upper() == 'TRUE'
        # the maximum log size in bytes
        self.max_log_size = int(env['MAX_LOG_SIZE'])

    def compute_image_name(self):
        '''Compute the main image name being built

        Uses the first available tag to produce a canonical image name for the
        current image build.
        '''
        self.image_name = '{}:{}'.format(self.docker_repo, self.docker_tags[0])
        os.environ["IMAGE_NAME"] = self.image_name

    def compute_cache_name(self):
        '''Compute the name of the image containing cache layers

        Uses the specified cache tag to produce a canonical image name for the
        image to pull to obtain the layers required for loading the cache.
        '''
        self.cache_name = '{}:{}'.format(self.docker_repo, self.cache_tag)

    def clone(self):
        '''Clone the build context from the user source repository
        '''
        if self.ssh_private:
            self.source_url = vcs.process_source_url(self.source_url)
        vcs.clone(self.source_type, self.source_url, self.source_branch,
                  self.source_commit, self.ssh_private)
        private_log.info("Cloning done")

    def prepare_build_context(self):
        '''Prepare the build context for build readiness

        Creates the build stage and clones the user source repository.
        '''
        startup.prepare_build_stage(self.build_code)
        self.clone()

    def resolve_paths(self):
        '''Compute paths relevant to the build step

        Once the build context is prepared this method computes paths relevant to
        the build step.
        '''
        self.build_path = utils.clean_path(self.build_path)
        self.build_path, self.dockerfile_path = startup.resolve_dockerfile_path(
            self.build_path, self.dockerfile_path)
        self.dockerfile_folder = os.path.dirname(
            os.path.join(self.build_path, self.dockerfile_path))
        self.readme_path = startup.resolve_readme_path(self.build_path,
                                                       self.dockerfile_folder)

    def post_dockerfile(self):
        '''Post the target Dockerfile to the configured url

        Uploads the Dockerfile contents to the configured signed url so it can be
        retrieved by clients at a later time.

        '''
        private_log.info("Getting Dockerfile")
        file_path = os.path.join(self.build_path, self.dockerfile_path)
        utils.post_to_url(self.signed_urls['post']['dockerfile'],
                          os.path.abspath(file_path), self.push_attempt_count)

    def post_readme(self):
        '''Post the README file in the source repository to the configured url

        Uploads the contents of a found README file to the configured signed url so it
        can be retrieved by clients at a later time.
        '''
        if self.readme_path:
            utils.post_to_url(self.signed_urls['post']['readme'],
                              os.path.abspath(self.readme_path),
                              self.push_attempt_count)

    def process_build_context(self):
        '''Process the build context to prepare it for building

        Once the build context is available this method performs a number of steps
        related to its contents in order to prepare for the build including uploading
        source assets and preparing any hooks.
        '''
        self.resolve_paths()
        self.post_dockerfile()
        self.post_readme()
        hooks.setup(self.dockerfile_folder)

    def snapshot_docker_state(self):
        '''Record current docker containers and image tags

        This records the current docker containers and image tags on the machine so
        that any introduced by the build process can be removed afterwards.
        '''
        self.original_tags = startup.snapshot_tags(self.client)
        self.original_containers = startup.snapshot_containers(self.client)

    def setup(self):
        '''Perform the preparations nessecary for building

        This method performs the steps before building can take place. This centrally
        revovles around cloning the build context and extracting source assets.
        '''
        public_log.step = 'setup'
        private_log.step = 'setup'
        startup.log_build_destination(self.byon)
        self.prepare_build_context()
        self.process_build_context()
        hooks.run('post_checkout')
        self.client = startup.login(self.docker_host, self.dockercfg)
        self.snapshot_docker_state()

    def _build(self):
        '''Perform the Docker image build

        This method performs the main image build and any configured tagging.
        '''
        hooks.run('pre_build')
        if not hooks.run('build'):
            build.log_docker_version(self.client)
            cache_repo = "{}:{}".format(
                self.docker_repo, self.cache_tag) if self.cache_tag else None
            build.build_image(self.client, self.build_path,
                              self.dockerfile_path, self.image_name,
                              cache_repo)
            build.multitag_image(self.client, self.image_name,
                                 self.docker_repo, self.docker_tags[1:])
            build.add_this_tag(self.client, self.image_name)
        hooks.run('post_build')

    def build(self):
        public_log.step = 'build'
        private_log.step = 'build'
        build_timer = metrics.timed('build_duration_seconds')
        build_timer.start()
        try:
            self._build()
        except:
            build_timer.stop(state="failure")
            raise
        else:
            build_timer.stop(state="success")

    def test(self):
        '''Perform any tests in the source repository
        '''
        public_log.step = 'test'
        private_log.step = 'test'
        hooks.run("pre_test")
        if not hooks.run("test"):
            test.test(self.client, self.build_code)
        hooks.run("post_test")

    def push(self):
        '''Push the built image to the registry
        '''
        if not self.should_push:
            return

        public_log.step = 'push'
        private_log.step = 'push'
        private_log.info("Starting Push")
        hooks.run('pre_push')
        if not hooks.run('push'):
            public_log.info("Pushing {}...".format(self.image_name))
            registry.push(self.client, self.docker_repo, self.docker_tags,
                          self.push_attempt_count)
            public_log.info("Done!")
        hooks.run('post_push')

    def pull(self):
        '''Pull the configured cache image
        '''
        if not self.cache_tag:
            return
        public_log.info("Pulling cache layers for {}...".format(
            self.cache_name))
        registry.pull(self.client, self.docker_repo, self.cache_tag,
                      self.push_attempt_count)
        public_log.info("Done!")

    def cleanup(self):
        '''Cleanup the build context and results of the build process
        '''
        public_log.step = 'cleanup'
        private_log.step = 'cleanup'
        try:
            if self.client:
                cleanup.remove_build_stage(self.build_code)
                cleanup.remove_build_containers(self.client,
                                                self.original_containers)
                cleanup.remove_build_tags(self.client, self.original_tags)
        except Exception:
            private_log.exception('Unexpected error while cleaning up')

    def handle_highland_error(self, exc):
        public_log.info(str(exc))
        return 2

    def handle_unknown_error(self, exc):
        public_log.info('Unexpected error')
        exc_info = traceback.format_exc()
        exc_msg = 'Encountered error: {}\n{}'.format(exc, exc_info)
        public_log.info(exc_msg)
        return 1

    def _run(self):
        '''Execute the steps of the build process
        '''
        try:
            self.setup()
            self.pull()
            self.build()
            self.test()
            self.push()
            public_log.info("Build finished")
        except errors.HighlandError as exc:
            return self.handle_highland_error(exc)
        except Exception as exc:
            return self.handle_unknown_error(exc)
        finally:
            self.cleanup()

    def run(self):
        '''Execute the full build process

        This method provides a logging carriage to ensure that any results of the build
        process are properly logged and uploaded.
        '''
        exit_code = 0
        try:
            exit_code = self._run()
        except Exception:
            private_log.exception("TOP-LEVEL EXCEPTION")
        finally:
            utils.post_to_url(self.signed_urls['post']['logs'], '/public.log')
            utils.post_to_url(self.signed_urls['post']['debug'],
                              '/private.log')
            utils.post_to_url(self.signed_urls['post']['metrics'],
                              '/metrics.log')
        return exit_code
