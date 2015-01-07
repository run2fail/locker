import unittest
import tempfile

from locker import Project

class LockerTest(unittest.TestCase):
    ''' Defines two containers that have not yet been created

    - The args are side effect free.
    - Creates project instance in setUp()
    - Cleans project instance in tearDown()
    - Does not create any containers
    - Does not start network instance
    '''

    def init_config(self, containers=[]):
        self.yml = {
            'containers': {
                'ubuntu': {
                    'template': {
                        'name':    "ubuntu",
                        'release': "trusty",
                        'arch':    "amd64",
                    },
                    "ports": [
                        "8000:8000",
                        "8000:8000/udp",
                        "8001:8001/tcp",
                        "192.168.2.123:8002:8002",
                        "192.168.2.123:8003:8003/tcp",
                        "192.168.2.123:8003:8003/udp",
                        "invalid",
                    ],
                    "fqdn": "test.example.net",
                    "dns": [
                        "8.8.8.8",
                        "$bridge",
                        "$copy",
                    ],
                    "links": [
                        "sshd:something",
                    ],
                    "cgroup": [
                        "memory.limit_in_bytes=200000000",
                    ],
                    "volumes": [
                        self.tmpdir.name + "/var/log:/var/log/",
                        self.tmpdir.name + "/foo:/bar",
                    ],
                },
                'sshd': {
                    'clone': 'test_ubuntu',
                    "links": [
                        "ubuntu",
                    ],
                }
            }
        }
        self.args = {
            'project':          'test',
            'containers':       containers,
            'verbose':          False,
            'lxcpath':          self.tmpdir.name,
            'no_ports':         False,
            'no_links':         False,
            'add_hosts':        False,
            'restart':          False,
            'force_delete':     True,
        }

    def setUp(self, containers=[]):
        self.tmpdir = tempfile.TemporaryDirectory(dir='/tmp/locker')
        self.init_config(containers)
        self.project = Project(self.yml, self.args)

    def tearDown(self):
        self.project.cleanup()
        self.tmpdir.cleanup()
