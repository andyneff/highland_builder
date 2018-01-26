import os
import logging
import subprocess

from builder import utils

public_log = logging.getLogger('public')


def setup(dockerfile_folder):
    os.chdir(dockerfile_folder)

    if os.path.isdir('hooks'):
        subprocess.call(['chmod', '-R', '+x', 'hooks'])


def run(name):
    hook_path = os.path.join('hooks', name)
    if os.path.isfile(hook_path):
        public_log.info('Executing {} hook...'.format(name))
        utils.execute_command(hook_path, '{} hook failed!'.format(name))
        return True
