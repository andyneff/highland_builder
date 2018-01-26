import os
import logging

from builder import errors, utils

public_log = logging.getLogger('public')
private_log = logging.getLogger('private')

# outputs from git to denote what failure occured
ACCESS_RIGHTS_SUBSTR = 'Please make sure you have the correct access rights'
NO_BRANCH_SUBSTR = 'not found in'


def process_source_url(source_url):
    # if the repository is a private github repository
    # ensure that we are using the ssh form of the git url
    if source_url.startswith("https://github.com"):
        source_url = source_url.replace("https://", "git@", 1)
        source_url = source_url.replace("/", ":", 1)
    return source_url


def write_private_key(contents, destination="~/.ssh/id_rsa", mode=0600):
    private_key_path = os.path.expanduser(destination)
    with open(private_key_path, 'w') as fd:
        fd.write(contents)
        fd.write('\n')
    os.chmod(private_key_path, mode)


def clone_commands_for_git(source_url,
                           source_branch,
                           source_commit=None,
                           bin_path='/usr/bin/git'):
    if source_commit:
        return [
            [bin_path, 'clone', '--recursive', source_url, '.'],
            [
                bin_path, 'checkout', '-B', source_branch or "master",
                source_commit
            ],
            [bin_path, 'submodule', 'update'],
        ]
    else:
        return [
            [
                bin_path, 'clone', '--recursive', '--depth', '1', '-b',
                source_branch or "master", source_url, '.'
            ],
            [bin_path, 'submodule', 'update'],
        ]


def clone_commands_for_hg(source_url,
                          source_branch,
                          source_commit=None,
                          bin_path='/usr/bin/hg'):
    return [
        [bin_path, 'clone', '-r', source_branch or "default", source_url, '.']
    ]


def get_clone_commands(source_type,
                       source_url,
                       source_branch,
                       source_commit=None):
    """
    Return a list of command parts suitable for Popen that will
    clone the source of the build context
    """
    delegates = {
        'git': clone_commands_for_git,
        'hg': clone_commands_for_hg,
    }
    delegate = delegates.get(source_type)

    if not delegate:
        options = ", ".join(delegates.keys())
        msg = "Invalid SCM type: %r must be one of {}" % options
        raise errors.HighlandError(msg)

    return delegate(source_url, source_branch, source_commit)


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


def export_git_details():
    os.environ['GIT_SHA1'] = utils.get_output(['git', 'rev-parse', 'HEAD'])
    os.environ['GIT_MSG'] = utils.get_output(
        ['git', 'log', '--format=%B', '-n', '1', os.environ['GIT_SHA1']])
    os.environ['COMMIT_MSG'] = os.environ['GIT_MSG']


def clone(source_type,
          source_url,
          source_branch,
          commit=None,
          private_key=None):
    """
    Clone the source of the build context and set it as the working directory
    """
    private_log.info("Starting to clone")
    if private_key:
        write_private_key(private_key)
    clone_commands = get_clone_commands(source_type, source_url, source_branch,
                                        commit)
    for clone_command in clone_commands:
        utils.execute_command(clone_command, convert_clone_error)
    if source_type == 'git':
        export_git_details()
    del os.environ['SOURCE_URL']
