import os
import json
import subprocess
import unittest
import uuid
import requests


class BaseTest(unittest.TestCase):
    _multiprocess_can_split_ = True

    '''
    BaseTest class provides initialization and teardown functionality
    for mendix buildpack tests that utilize cloudfoundry
    '''

    def __init__(self, *args, **kwargs):
        super(BaseTest, self).__init__(*args, **kwargs)
        if not os.environ.get("TRAVIS_BRANCH"):
            current_branch = subprocess.check_output("git rev-parse --symbolic-full-name --abbrev-ref HEAD", shell=True)
        else:
            current_branch = "master"
        self.cf_domain = os.environ.get("CF_DOMAIN")
        assert self.cf_domain
        self.branch_name = os.environ.get("TRAVIS_BRANCH", current_branch)
        self.mx_password = os.environ.get("MX_PASSWORD", "Y0l0lop13#123")
        self.app_id = str(uuid.uuid4()).split("-")[0]
        self.subdomain = "ops-" + self.app_id
        self.app_name = "%s.%s" % (self.subdomain, self.cf_domain)

    def startApp(self):
        try:
            self.cmd(('cf', 'start', self.app_name))
        except subprocess.CalledProcessError as e:
            print((self.get_recent_logs()))
            raise e

    def setUpCF(self, package_name, env_vars=None):
        try:
            self._setUpCF(package_name, env_vars=env_vars)
        except:
            self.tearDown()
            raise

    def _setUpCF(self, package_name, env_vars=None):
        self.package_name = package_name
        self.package_url = os.environ.get(
            "PACKAGE_URL",
            "https://s3-eu-west-1.amazonaws.com/mx-ci-binaries/" + package_name
        )

        self.cmd((
            'wget', '--quiet', '-c',
            '-O', self.app_id + self.package_name,
            self.package_url,
        ))
        try:
            subprocess.check_output((
                'cf', 'push', self.app_name,
                '-d', self.cf_domain,
                '-p', self.app_id + self.package_name,
                '-n', self.subdomain,
                '--no-start',
                '-k', '3G',
                '-m', '2G',
                '-b', (
                    'https://github.com/mendix/cf-mendix-buildpack.git#%s'
                    % self.branch_name
                ),
            ), stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            print((e.output))
            raise

        self.cmd((
            './create-app-services.sh', self.app_name
        ))

        app_guid = subprocess.check_output(('cf', 'app', self.app_name, '--guid')).strip()

        environment = {
            'ADMIN_PASSWORD': self.mx_password,
            'DEBUGGER_PASSWORD': self.mx_password,
            'DEVELOPMENT_MODE': 'true',
            'S3_USE_SSE': 'true',
            'USE_DATA_SNAPSHOT': 'true',
        }

        if env_vars is not None:
            environment.update(env_vars)

        subprocess.check_output((  # check_call prints the output, no thanks
            'cf', 'curl', '-X', 'PUT',
            '/v2/apps/%s' % app_guid,
            '-d', json.dumps({"environment_json": environment})
        ))

    def tearDown(self):
        self.cmd(('./delete-app.sh', self.app_name))

    def assert_app_running(self, app_name, path="/xas/", code=401):
        full_uri = "https://" + app_name + path
        r = requests.get(full_uri)
        assert r.status_code == code

    def get_recent_logs(self):
        return subprocess.check_output((
            'cf', 'logs', self.app_name, '--recent',
        ))

    def assert_string_in_recent_logs(self, app_name, substring):
        output = subprocess.check_output(('cf', 'logs', app_name, '--recent'))
        if output.find(substring) > 0:
            pass
        else:
            print(output)
            self.fail('Failed to find substring in recent logs: ' + substring)

    def cmd(self, command):
        subprocess.check_call(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
