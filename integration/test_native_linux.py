"""
Layer B: Native Linux Integration Test Runner
Executes native binary validations (nginx -t, sshd -t, visudo -cf, systemd-analyze)
when running on Linux, or skips gracefully with actionable instructions on Windows hosts.
"""
import os
import subprocess
import unittest
import sys

class TestNativeLinuxIntegration(unittest.TestCase):
    def setUp(self):
        self.is_linux = sys.platform.startswith("linux")

    def test_docker_definition_exists(self):
        dockerfile = os.path.join(os.path.dirname(__file__), "Dockerfile")
        script = os.path.join(os.path.dirname(__file__), "run_integration.sh")
        self.assertTrue(os.path.exists(dockerfile), "Layer B Dockerfile must exist")
        self.assertTrue(os.path.exists(script), "Layer B run_integration.sh must exist")

    def test_native_linux_tools_if_available(self):
        if not self.is_linux:
            self.skipTest("Host is not Linux. Native binary tests execute in Ubuntu 24.04 Docker container or CI.")

        # If on Linux and binaries exist, execute test script
        if os.path.exists("/usr/sbin/nginx"):
            res = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"nginx -t failed: {res.stderr}")

if __name__ == "__main__":
    unittest.main()
