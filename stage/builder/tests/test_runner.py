import os
import mock

from builder import runner, errors
from builder.tests.utils import PatchCase, easy_dict


class RunnerInitCase(PatchCase):
    mocks = {
        'gather': 'builder.runner.BuildRunner.gather_environment',
        'image_name': 'builder.runner.BuildRunner.compute_image_name',
        'cache_name': 'builder.runner.BuildRunner.compute_cache_name'
    }

    def test_init(self):
        b = runner.BuildRunner()
        self.mock_gather.assert_called_with(os.environ)
        assert b.client is None
        assert self.mock_image_name.called
        assert self.mock_cache_name.called

    def test_custom_env(self):
        env = {'foo': 'bar'}
        runner.BuildRunner(env)
        self.mock_gather.assert_called_with(env)


class RunnerGatherEnvironmentCase(PatchCase):
    mocks = {'loads': 'json.loads', 'env': 'os.environ'}

    def get_base_env(self):
        env = easy_dict(
            'BUILD_CODE', 'DOCKER_REPO', 'DOCKER_TAG', 'SOURCE_TYPE',
            'SOURCE_URL', 'SOURCE_BRANCH', 'SOURCE_COMMIT', 'SSH_PRIVATE',
            'BUILD_PATH', 'DOCKERFILE_PATH', 'DOCKER_HOST', 'DOCKERCFG',
            'CACHE_TAG', 'SIGNED_URLS', 'BYON', 'PUSH', 'PUSH_ATTEMPT_COUNT',
            'LOG_BUILD_STEPS', 'MAX_LOG_SIZE')
        env.update({
            'PUSH_ATTEMPT_COUNT': 1,
            'MAX_LOG_SIZE': 1,
        })
        return env

    def test_gathered(self):
        env = self.get_base_env()
        b = runner.BuildRunner(env)
        assert b.build_code == env['BUILD_CODE']
        assert b.docker_repo == env['DOCKER_REPO']
        assert b.docker_tags == [env['DOCKER_TAG']]
        assert b.docker_tag == env['DOCKER_TAG']
        assert b.source_type == env['SOURCE_TYPE']
        assert b.source_url == env['SOURCE_URL']
        assert b.source_branch == env['SOURCE_BRANCH']
        assert b.source_commit == env['SOURCE_COMMIT']
        assert b.ssh_private == env['SSH_PRIVATE']
        assert b.build_path == env['BUILD_PATH']
        assert b.dockerfile_path == env['DOCKERFILE_PATH']
        assert b.docker_host == env['DOCKER_HOST']
        assert b.dockercfg == env['DOCKERCFG']
        assert b.cache_tag == env['CACHE_TAG']
        assert b.signed_urls._mock_new_parent == self.mock_loads
        assert b.byon == env['BYON']
        assert b.should_push == bool(env['PUSH'] == 'TRUE')
        assert b.push_attempt_count == env['PUSH_ATTEMPT_COUNT']
        assert b.log_build_steps == bool(env['LOG_BUILD_STEPS'] == 'TRUE')
        assert b.max_log_size == env['MAX_LOG_SIZE']

    def test_gathered_defaults(self):
        env = self.get_base_env()
        del env['DOCKER_TAG']
        del env['SOURCE_BRANCH']
        del env['SOURCE_COMMIT']
        del env['SSH_PRIVATE']
        del env['BUILD_PATH']
        del env['DOCKERFILE_PATH']
        del env['BYON']
        del env['PUSH']
        del env['PUSH_ATTEMPT_COUNT']
        del env['LOG_BUILD_STEPS']
        b = runner.BuildRunner(env)
        assert b.docker_tag == 'latest'
        assert b.source_branch is None
        assert b.source_commit is None
        assert b.ssh_private is None
        assert b.build_path == '/'
        assert b.dockerfile_path == ''
        assert b.byon is None
        assert b.should_push is False
        assert b.push_attempt_count == 5
        assert b.log_build_steps is False


class MockedRunnerCase(PatchCase):
    def mockUp(self):
        env_patch = mock.patch('os.environ', dict())
        self.mock_env = env_patch.start()
        self.addCleanup(env_patch.stop)
        self.mock_runner = mock.MagicMock()
        self.mock_runner.__class__ = runner.BuildRunner


class ComputeImageNameCase(MockedRunnerCase):
    def test_image_name(self):
        self.mock_runner.docker_repo = 'repo'
        self.mock_runner.docker_tags = ['tag']
        runner.BuildRunner.compute_image_name(self.mock_runner)
        assert self.mock_runner.image_name == "repo:tag"


class ComputeCacheNameCase(MockedRunnerCase):
    def test_cache_name(self):
        self.mock_runner.docker_repo = 'repo'
        self.mock_runner.cache_tag = 'tag'
        runner.BuildRunner.compute_cache_name(self.mock_runner)
        assert self.mock_runner.cache_name == "repo:tag"


class CloneCase(MockedRunnerCase):
    mocks = {
        'source_url': 'builder.vcs.process_source_url',
        'clone': 'builder.vcs.clone',
        'log': 'builder.runner.public_log'
    }

    def test_private_key(self):
        self.mock_runner.ssh_private = 'key'
        runner.BuildRunner.clone(self.mock_runner)
        assert self.mock_runner.source_url._mock_new_parent == self.mock_source_url

    def test_no_private_key(self):
        self.mock_runner.ssh_private = None
        runner.BuildRunner.clone(self.mock_runner)
        assert not self.mock_source_url.called

    def test_cloned(self):
        self.mock_runner.source_type = 'type'
        self.mock_runner.source_url = 'url'
        self.mock_runner.source_branch = 'branch'
        self.mock_runner.source_commit = 'commit'
        self.mock_runner.ssh_private = None
        runner.BuildRunner.clone(self.mock_runner)
        self.mock_clone.assert_called_with('type', 'url', 'branch', 'commit',
                                           None)


class PrepareBuildContextCase(MockedRunnerCase):
    mocks = {'prepare': 'builder.startup.prepare_build_stage'}

    def test_prepared(self):
        self.mock_runner.build_code = 'code'
        runner.BuildRunner.prepare_build_context(self.mock_runner)
        self.mock_prepare.assert_called_with('code')
        assert self.mock_runner.clone.called


class ResolvePathsCase(MockedRunnerCase):
    mocks = {
        'clean': 'builder.utils.clean_path',
        'dockerfile': 'builder.startup.resolve_dockerfile_path',
        'readme': 'builder.startup.resolve_readme_path',
        'chdir': 'os.chdir'
    }

    def test_paths(self):
        self.mock_runner.build_path = 'path'
        self.mock_runner.dockerfile_path = 'dockerfile'
        self.mock_clean.return_value = 'clean'
        self.mock_dockerfile.return_value = 'build_path', 'dockerfile'
        self.mock_readme.return_value = 'readme'
        runner.BuildRunner.resolve_paths(self.mock_runner)
        assert self.mock_runner.build_path == 'build_path'
        assert self.mock_runner.dockerfile_path == 'dockerfile'
        assert self.mock_runner.readme_path == 'readme'
        self.mock_clean.assert_called_with('path')
        self.mock_dockerfile.assert_called_with('clean', 'dockerfile')
        self.mock_readme.assert_called_with('build_path', 'build_path')


class PostDockerfileCase(MockedRunnerCase):
    mocks = {
        'log': 'builder.runner.public_log',
        'join': 'os.path.join',
        'post': 'builder.utils.post_to_url'
    }

    def test_post(self):
        self.mock_runner.signed_urls = {'post': {'dockerfile': 'spec'}}
        self.mock_runner.push_attempt_count = 'count'
        self.mock_join.return_value = 'join'
        runner.BuildRunner.post_dockerfile(self.mock_runner)
        self.mock_post.assert_called_with('spec', 'join', 'count')


class PostReadmeCase(MockedRunnerCase):
    mocks = {'post': 'builder.utils.post_to_url', 'abspath': 'os.path.abspath'}

    def test_has_path(self):
        self.mock_runner.push_attempt_count = 'count'
        self.mock_runner.signed_urls = {'post': {'readme': 'spec'}}
        self.mock_runner.readme_path = 'readme'
        self.mock_abspath.return_value = 'readme_abspath'
        runner.BuildRunner.post_readme(self.mock_runner)
        self.mock_post.assert_called_with('spec', 'readme_abspath', 'count')

    def test_missing_path(self):
        self.mock_runner.readme_path = None
        runner.BuildRunner.post_readme(self.mock_runner)
        assert not self.mock_post.called


class ProcessBuildContextCase(MockedRunnerCase):
    mocks = {'setup': 'builder.hooks.setup'}

    def test_procesed(self):
        runner.BuildRunner.process_build_context(self.mock_runner)
        assert self.mock_runner.resolve_paths.called
        assert self.mock_runner.post_dockerfile.called
        assert self.mock_runner.post_readme.called
        assert self.mock_setup.called


class SnapshotDockerStateCase(MockedRunnerCase):
    mocks = {
        'tags': 'builder.startup.snapshot_tags',
        'containers': 'builder.startup.snapshot_containers'
    }

    def test_snapshot(self):
        self.mock_runner.client = 'client'
        self.mock_tags.return_value = 'tags'
        self.mock_containers.return_value = 'containers'
        runner.BuildRunner.snapshot_docker_state(self.mock_runner)
        self.mock_tags.assert_called_with('client')
        self.mock_containers.assert_called_with('client')
        assert self.mock_runner.original_tags == 'tags'
        assert self.mock_runner.original_containers == 'containers'


class SetupCase(MockedRunnerCase):
    mocks = {
        'log': 'builder.runner.public_log',
        'destination': 'builder.startup.log_build_destination',
        'run': 'builder.hooks.run',
        'login': 'builder.startup.login'
    }

    def mockUp(self):
        super(SetupCase, self).mockUp()
        self.mock_runner.byon = 'byon'
        self.mock_runner.docker_host = 'host'
        self.mock_runner.dockercfg = 'cfg'

    def test_step_set(self):
        runner.BuildRunner.setup(self.mock_runner)
        assert self.mock_log.step == 'setup'

    def test_hook_ran(self):
        runner.BuildRunner.setup(self.mock_runner)
        self.mock_run.assert_called_with('post_checkout')

    def test_setup(self):
        runner.BuildRunner.setup(self.mock_runner)
        assert self.mock_runner.prepare_build_context.called
        assert self.mock_runner.process_build_context.called
        assert self.mock_runner.snapshot_docker_state.called

    def test_login(self):
        runner.BuildRunner.setup(self.mock_runner)
        assert self.mock_runner.client._mock_new_parent == self.mock_login
        self.mock_login.assert_called_with('host', 'cfg')


class PrivateBuildCase(MockedRunnerCase):
    mocks = {
        'public_log': 'builder.runner.public_log',
        'private_log': 'builder.runner.private_log',
        'metrics': 'builder.runner.metrics',
        'run': 'builder.hooks.run',
        'version': 'builder.build.log_docker_version',
        'build': 'builder.build.build_image',
        'multitag': 'builder.build.multitag_image',
        'add_this': 'builder.build.add_this_tag'
    }

    def mockUp(self):
        super(PrivateBuildCase, self).mockUp()
        self.mock_runner.client = 'client'
        self.mock_runner.build_path = 'build_path'
        self.mock_runner.dockerfile_path = 'dockerfile'
        self.mock_runner.image_name = 'image'
        self.mock_runner.cache_tag = 'cache'
        self.mock_runner.docker_repo = 'repo'
        self.mock_runner.docker_tags = ['tag']

    def test_pre_build_hook(self):
        runner.BuildRunner._build(self.mock_runner)
        assert mock.call("pre_build") in self.mock_run.mock_calls

    def test_build_hook(self):
        self.mock_run.return_value = True
        runner.BuildRunner._build(self.mock_runner)
        assert not self.mock_version.called
        assert not self.mock_build.called
        assert not self.mock_multitag.called
        assert not self.mock_add_this.called
        assert mock.call("post_build") in self.mock_run.mock_calls

    def test_build(self):
        self.mock_run.return_value = False
        runner.BuildRunner._build(self.mock_runner)
        self.mock_version.assert_called_with('client')
        self.mock_build.assert_called_with('client', 'build_path',
                                           'dockerfile', 'image', 'repo:cache')
        self.mock_multitag.assert_called_with('client', 'image', 'repo', [])
        self.mock_add_this.assert_called_with('client', 'image')
        assert mock.call("post_build") in self.mock_run.mock_calls


class BuildCase(MockedRunnerCase):
    mocks = {
        'private_log': 'builder.runner.private_log',
        'public_log': 'builder.runner.public_log',
        'metrics': 'builder.runner.metrics'
    }

    def mockUp(self):
        super(BuildCase, self).mockUp()
        self.mock_timer = mock.MagicMock()
        self.mock_metrics.timed.return_value = self.mock_timer

    def test_step_set(self):
        runner.BuildRunner.build(self.mock_runner)
        assert self.mock_private_log.step == 'build'
        assert self.mock_public_log.step == 'build'

    def test_timer(self):
        runner.BuildRunner.build(self.mock_runner)
        assert self.mock_timer.start.called
        self.mock_timer.stop.assert_called_with(state='success')

    def test_exception(self):
        self.mock_runner._build.side_effect = Exception
        with self.assertRaises(Exception):
            runner.BuildRunner.build(self.mock_runner)
        assert self.mock_timer.start.called
        self.mock_timer.stop.assert_called_with(state='failure')


class TestCase(MockedRunnerCase):

    mocks = {
        'log': 'builder.runner.public_log',
        'run': 'builder.hooks.run',
        'test': 'builder.test.test'
    }

    def mockUp(self):
        super(TestCase, self).mockUp()
        self.mock_runner.client = 'client'
        self.mock_runner.build_code = 'code'

    def test_step_set(self):
        runner.BuildRunner.test(self.mock_runner)
        assert self.mock_log.step == 'test'

    def test_pre_test_hook(self):
        runner.BuildRunner.test(self.mock_runner)
        assert mock.call("pre_test") in self.mock_run.mock_calls

    def test_post_test_hook(self):
        runner.BuildRunner.test(self.mock_runner)
        assert mock.call("post_test") in self.mock_run.mock_calls

    def test_test(self):
        self.mock_run.return_value = False
        runner.BuildRunner.test(self.mock_runner)
        self.mock_test.assert_called_with('client', 'code')

    def test_test_hook(self):
        self.mock_run.return_value = True
        runner.BuildRunner.test(self.mock_runner)
        assert not self.mock_test.called


class PushCase(MockedRunnerCase):

    mocks = {
        'log': 'builder.runner.public_log',
        'run': 'builder.hooks.run',
        'push': 'builder.registry.push'
    }

    def mockUp(self):
        super(PushCase, self).mockUp()
        self.mock_runner.image_name = 'image'
        self.mock_runner.client = 'client'
        self.mock_runner.build_code = 'code'
        self.mock_runner.docker_repo = 'repo'
        self.mock_runner.docker_tags = ['tag']
        self.mock_runner.push_attempt_count = 1

    def test_step_set(self):
        runner.BuildRunner.push(self.mock_runner)
        assert self.mock_log.step == 'push'

    def test_pre_push_hook(self):
        runner.BuildRunner.push(self.mock_runner)
        assert mock.call("pre_push") in self.mock_run.mock_calls

    def test_post_push_hook(self):
        runner.BuildRunner.push(self.mock_runner)
        assert mock.call("post_push") in self.mock_run.mock_calls

    def test_push(self):
        self.mock_run.return_value = False
        runner.BuildRunner.push(self.mock_runner)
        self.mock_push.assert_called_with('client', 'repo', ['tag'], 1)

    def test_push_hook(self):
        self.mock_run.return_value = True
        runner.BuildRunner.push(self.mock_runner)
        assert not self.mock_push.called


class PullCase(MockedRunnerCase):

    mocks = {
        'log': 'builder.runner.public_log',
        'pull': 'builder.registry.pull'
    }

    def mockUp(self):
        super(PullCase, self).mockUp()
        self.mock_runner.client = 'client'
        self.mock_runner.docker_repo = 'repo'
        self.mock_runner.cache_tag = 'tag'
        self.mock_runner.push_attempt_count = 1

    def test_pull(self):
        runner.BuildRunner.pull(self.mock_runner)
        self.mock_pull.assert_called_with('client', 'repo', 'tag', 1)


class CleanupCase(MockedRunnerCase):

    mocks = {
        'log': 'builder.runner.public_log',
        'stage': 'builder.cleanup.remove_build_stage',
        'containers': 'builder.cleanup.remove_build_containers',
        'tags': 'builder.cleanup.remove_build_tags',
        'format': 'traceback.format_exc'
    }

    def mockUp(self):
        super(CleanupCase, self).mockUp()
        self.mock_runner.build_code = 'code'
        self.mock_runner.client = 'client'
        self.mock_runner.original_containers = 'containers'
        self.mock_runner.original_tags = 'tags'

    def test_step_set(self):
        runner.BuildRunner.cleanup(self.mock_runner)
        assert self.mock_log.step == 'cleanup'

    def test_has_client(self):
        runner.BuildRunner.cleanup(self.mock_runner)
        self.mock_stage.assert_called_with('code')
        self.mock_containers.assert_called_with('client', 'containers')
        self.mock_tags.assert_called_with('client', 'tags')

    def test_missing_client(self):
        self.mock_runner.client = None
        runner.BuildRunner.cleanup(self.mock_runner)
        assert not self.mock_stage.called
        assert not self.mock_containers.called
        assert not self.mock_tags.called

    def test_catches_exception(self):
        self.mock_stage.side_effect = Exception()
        runner.BuildRunner.cleanup(self.mock_runner)


class HandleHighlandError(MockedRunnerCase):
    mocks = {'log': 'builder.runner.public_log'}

    def test_handler(self):
        result = runner.BuildRunner.handle_highland_error(self.mock_runner,
                                                          'foo')
        assert result == 2
        self.mock_log.info.assert_called_with('foo')


class HandleUnknownError(MockedRunnerCase):
    mocks = {
        'log': 'builder.runner.public_log',
        'format': 'traceback.format_exc'
    }

    def test_handler(self):
        result = runner.BuildRunner.handle_unknown_error(self.mock_runner,
                                                         'foo')
        assert result == 1


class PrivateRunCase(MockedRunnerCase):

    mocks = {'log': 'builder.runner.public_log'}

    def test_run(self):
        result = runner.BuildRunner._run(self.mock_runner)
        assert result is None
        assert self.mock_runner.setup.called
        assert self.mock_runner.build.called
        assert self.mock_runner.test.called
        assert self.mock_runner.push.called
        assert self.mock_runner.cleanup.called

    def test_highland_error(self):
        self.mock_runner.setup.side_effect = errors.HighlandError()
        result = runner.BuildRunner._run(self.mock_runner)
        assert result._mock_new_parent == self.mock_runner.handle_highland_error
        assert self.mock_runner.cleanup.called

    def test_unknown_error(self):
        self.mock_runner.setup.side_effect = Exception()
        result = runner.BuildRunner._run(self.mock_runner)
        assert result._mock_new_parent == self.mock_runner.handle_unknown_error
        assert self.mock_runner.cleanup.called


class RunCase(MockedRunnerCase):
    mocks = {
        'tempfile': 'tempfile.NamedTemporaryFile',
        'log': 'builder.runner.public_log',
        'post': 'builder.utils.post_to_url'
    }

    def mockUp(self):
        super(RunCase, self).mockUp()
        # ugh context managers are such a pita..
        self.mock_runner.signed_urls = {
            'post': {
                'logs': 'logs',
                'debug': 'debug',
                'metrics': 'metrics'
            }
        }

    def test_exit_code(self):
        self.mock_runner._run.return_value = 'run'
        assert runner.BuildRunner.run(self.mock_runner) == 'run'

    def test_log_posted(self):
        runner.BuildRunner.run(self.mock_runner) == 'run'
        self.mock_post.mock_calls == [
            mock.call('logs', '/public.log'),
            mock.call('logs', '/private.log'),
            mock.call('logs', '/metrics.log'),
        ]
