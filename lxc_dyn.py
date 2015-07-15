#!/usr/bin/env python3

import os
import sys
import shlex
import shutil
import subprocess
import binascii

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
        sys.exit("You must be root run lxc")

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
        return shlex.split("virtualenv -p /usr/bin/python3 {0}".format(self.venv_path))

    def _activate(self):
        ''' activate the virtualenv '''
        activate_path = os.path.join(self.venv_path, "bin/activate_this.py")
        with open(activate_path) as f:
            code = compile(f.read(), activate_path, 'exec')
            exec(code, dict(__file__=activate_path))

    def create(self, *args, **kwargs):
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

    def destroy(self, *args, **kwargs):
        ''' destroy the virtualenv
            this rm -rfs, be really careful here if you are using custom
            venv_paths.
            TODO: add a guard against this with cli args
        '''
        subprocess.call(shlex.split(("rm -rf {0}".format(self.venv_path))))

def exec_ssh_agent(ssh_key='', cmd=''):
    """ wrapper to exec command with ssh-agent """
    return os.system('eval $(ssh-agent) && ssh-add {} && {}'.format(ssh_key, cmd))

def exec_user(username='', cmd=''):
    """ run cmd as username instead of root """
    return os.system('sudo -u {} {}'.format(username, cmd))

def exec_su_user(username='', cmd=''):
    """ run cmd as username instead of root with su because javascript"""
    return os.system('sudo su {} -c "{}"'.format(username, cmd))

class Oslxc():
    def __init__(self, name, username='', container=None, password='', template="ubuntu", template_args=None):
        """ manages a container
            :param: :name - name of the container
            :param: :username - the user to exec commands in container
            :param: :container - modify an already existing container
            :param: :password - the default password to create
            :param: :template - template to create the container from
        """
        self.name = name + binascii.hexlify(os.urandom(8)).decode('utf-8')
        self.username = username if username else os.environ.get('SUDO_USER', os.environ.get('USER', None))
        self.password = password if password else self.username
        self.subcontainers = False
        self.template = template
        self.template_args = template_args if template_args else {
            "release": "trusty",
            "arch": "amd64",
            "user": self.username,
            "auth-key": "{}/.ssh/authorized_keys".format(os.environ.get('HOME')),
            "packages": "python-virtualenv,python3,python3-pip",
            }

        self.container = container if container else self.create()

    def create(self):
        if os.getuid() == 0:
            container = lxc.Container(self.name)
            container.create(self.template, 0, self.template_args)
            container.start()
            return container
        else:
            return None

    def run(self, cmd=None, argv=(), env=None):
        env = env if env else ()
        self.container.attach_wait(cmd, argv, extra_env_vars=env)

    def _ssh_load_keys(self, keys=()):
        """ returns a dict with { key_path: key_text }
            :param: :keys - list of paths for the ssh keys
        """
        return dict(zip([ k for k in keys ], [ open(k, 'r').read() for k in keys ]))

    def ssh_key_add(self, key_paths=(), blacklist=(), key_dest=""):
        """ adds private and public key_paths to container
            :param: :key_paths - list of key_paths on the host to add to container
            :param: :blacklist - list of filenames on host to ignore when adding to container
            :param: :key_dest - the destination on the container to add ssh keys to
        """
        keys = self._ssh_load_keys(set(key_paths).difference(blacklist))
        def _(args=("", "", "")):
            key_path=args[0]
            key_data=args[1]
            key_dest=args[2]

            if not key_dest:
                key_dest = "/home/{}/.ssh".format(self.username)

            lxc_key_dest = os.path.join(key_dest, os.path.basename(key_path))

            with open(lxc_key_dest, 'w') as f:
                f.write(key_data)

            os.chmod(lxc_key_dest, 0o600)
            shutil.chown(lxc_key_dest, self.username, self.username)

        [ self.run(_, (key_path, key_data, key_dest)) for key_path, key_data in keys.items() ]

    def sudo_nopasswd(self, args=()):
        """ give self.username passwordless sudo """

        if not args:
            args = (self.username, )

        def _(args=()):
            """ args[0] == username to give passwordless sudo to """
            sudo_path='/etc/sudoers.d/{}'.format(args[0])
            sudo_str='%{} ALL=(ALL) NOPASSWD:ALL'.format(args[0])

            with open(sudo_path, 'w') as f:
                f.write(sudo_str)
        self.run(_, args)

def main():
    # todo tests
    v = Virtualenv('test', 'bmoar')
    def _():
        subprocess.call(shlex.split('pip freeze'))
    def install_flask():
        subprocess.call(shlex.split('pip install flask'))

    # clean env
    os.environ['PS1'] = '$ '

    ct = Oslxc('derp')

    import time
    while not ct.container.get_ips():
        time.sleep(1)

    ct.run(
    v.destroy
    )
    ct.run(
    v.create
    )
    ct.run(
    v.run,
    _
    )
    ct.run(
    v.run,
    install_flask
    )
    ct.run(
    v.run,
    _
    )

if __name__ == '__main__':
    main()
