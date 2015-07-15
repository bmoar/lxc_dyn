#!/usr/bin/env python3

import os
import sys
import shlex
import shutil
import subprocess

class Virtualenv():
    ''' wrapper for running code in a virtualenv
        :param: :name - name of the virtualenv
        :param: :usr - name of user to create cmd as if sudo
        :param: :init_cmd - a def() to run to create the venv, defaults to python3
        :param: :venv_path - '$HOME/.virtualenvs' by default
    '''

    def __init__(self, name, usr, init_cmd=None, venv_path=''):
        self.name = name
        self.usr = usr
        self.venv_path = venv_path if venv_path else self._get_default_path()
        self.init_cmd = init_cmd if init_cmd else self._default_cmd()

    def _get_default_path(self):
        ''' Gets the default path for the virtualenv
            if sudo: create it under self.usr home dir instead of root
        '''
        if os.getuid() == 0:
            return os.path.join(os.getenv('HOME').replace(os.getenv('SUDO_USER', ''), self.usr),
                    '.virtualenvs', self.name)
        else:
            return os.path.join(os.getenv('HOME'), '.virtualenvs', self.name)

    def _default_cmd(self):
        ''' a sane default a virtualenv path '''
        return shlex.split("virtualenv -p /usr/bin/python3 {}".format(self.venv_path))

    def _activate(self):
        ''' activate the virtualenv '''
        activate_path = os.path.join(self.venv_path, "bin/activate_this.py")
        with open(activate_path) as f:
            code = compile(f.read(), activate_path, 'exec')
            exec(code, dict(__file__=activate_path))

    def create(self):
        ''' create the virtualenv if it doesn't exist '''
        if not os.path.exists(self.venv_path):
            os.makedirs(self.venv_path, mode=0o755, exist_ok=True)
            shutil.chown(self.venv_path, self.usr, self.usr)
            return subprocess.call(self.init_cmd)
        else:
            return 0

    # [shortcuts]
    def install_ansible(self, args=None):
        return os.system('pip install ansible')

    def run(self, cmd):
        ''' run cmd with argv inside virtualenv '''
        self._activate()
        return cmd()

    def destroy(self):
        ''' destroy the virtualenv
            this rm -rfs, be really careful here if you are using custom
            venv_paths.
            TODO: add a guard against this with cli args
        '''
        subprocess.call(shlex.split(("rm -rf {0}".format(self.venv_path))))

# do self imports
try:
    import lxc
except ImportError:
    if os.getuid() == 0:
        if os.path.exists('/usr/bin/apt-get'):
            [ subprocess.call(x) for x in [
                'sudo apt-get update',
                'sudo apt-get install python-lxc',
                ]
            ]
        else:
            sys.exit("Todo: impliment better os checking")
    else:
        sys.exit("You must be root run, the lxc library depends on running as root")

def main():
    v = Virtualenv('test', 'bmoar')
    def _():
        subprocess.call(shlex.split('pip freeze'))
    def install_flask():
        subprocess.call(shlex.split('pip install flask'))

    v.destroy()
    v.create()
    v.run(_)
    v.run(install_flask)
    v.run(v.install_ansible)
    v.run(_)

if __name__ == '__main__':
    main()
