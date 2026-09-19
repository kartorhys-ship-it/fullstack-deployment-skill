"""
Unit tests for Layer A Simulation Sandbox
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sandbox.mock_host import MockHost
from sandbox.http_verifier import BehavioralHttpVerifier, is_trusted_cloudflare_ip

class TestSandboxSimulation(unittest.TestCase):
    def setUp(self):
        self.host = MockHost()

    def test_ufw_lockout_prevention(self):
        # 1. Enabling UFW without SSH causes lockout
        self.host.apply_ufw_rule("default deny incoming")
        success = self.host.enable_ufw()
        self.assertFalse(success)
        self.assertFalse(self.host.active_ssh_session)

        # 2. Enabling UFW with SSH keeps session active
        host2 = MockHost()
        host2.apply_ufw_rule("default deny incoming")
        host2.apply_ufw_rule("allow 22/tcp")
        success2 = host2.enable_ufw()
        self.assertTrue(success2)
        self.assertTrue(host2.active_ssh_session)

    def test_cloudflare_spoof_defense(self):
        # Trusted Cloudflare IP -> CF-Connecting-IP accepted
        cf_ip = "173.245.48.10"
        resolved = BehavioralHttpVerifier.verify_cloudflare_real_ip_resolution(
            cf_ip, {"CF-Connecting-IP": "203.0.113.19"}
        )
        self.assertEqual(resolved, "203.0.113.19")

        # Untrusted attacker IP -> spoofed header rejected
        attacker_ip = "198.51.100.5"
        resolved2 = BehavioralHttpVerifier.verify_cloudflare_real_ip_resolution(
            attacker_ip, {"CF-Connecting-IP": "203.0.113.19"}
        )
        self.assertEqual(resolved2, "198.51.100.5")

    def test_dynamic_csp_nonces(self):
        valid, nonce = BehavioralHttpVerifier.generate_and_verify_csp_nonce()
        self.assertTrue(valid)
        self.assertTrue(len(nonce) >= 16)

    def test_failure_injection_rollback(self):
        self.host.set_symlink("/var/www/webapp/previous", "/var/www/webapp/releases/v1")
        self.host.set_symlink("/var/www/webapp/current", "/var/www/webapp/releases/v2")

        recovered = BehavioralHttpVerifier.simulate_failure_and_verify_rollback(
            self.host, "/var/www/webapp/current", "/var/www/webapp/previous"
        )
        self.assertTrue(recovered)
        self.assertEqual(self.host.read_symlink("/var/www/webapp/current"), "/var/www/webapp/releases/v1")

if __name__ == "__main__":
    unittest.main()
