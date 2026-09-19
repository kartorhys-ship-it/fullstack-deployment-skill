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

        # Check if running as root (e.g., inside containerized testbed)
        if hasattr(os, "geteuid") and os.geteuid() == 0 and os.path.exists("/app/integration/run_integration.sh"):
            res = subprocess.run(["bash", "/app/integration/run_integration.sh"], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"run_integration.sh failed:\n{res.stdout}\n{res.stderr}")
        else:
            self.skipTest("Host Linux environment is non-root. Native integration tests run in containerized testbed via Docker.")

if __name__ == "__main__":
    unittest.main()
