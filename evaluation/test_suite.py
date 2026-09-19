"""
Consolidated Unit and Integration Test Suite
Validates harness core, policy engine, T0-T5 contracts, secrets, and state manager.
"""
import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from harness.policy import PolicyEngine, PolicyViolation, PreconditionFailure
from harness.secrets import SecretMasker
from harness.state import StateManager
from harness.tools import DeploymentTools, HumanApprovalRequired
from harness.core import DeploymentHarness, HarnessExecutionBudgetExceeded

class TestPolicyEngine(unittest.TestCase):
    def test_prohibited_commands(self):
        with self.assertRaises(PolicyViolation):
            PolicyEngine.validate_command_safety("rm -rf /")

        with self.assertRaises(PolicyViolation):
            PolicyEngine.validate_command_safety("rm -rf /var/www/webapp")

        with self.assertRaises(PolicyViolation):
            PolicyEngine.validate_command_safety("chmod 777 /var/www/webapp/shared")

    def test_secret_detection(self):
        # Raw password without placeholder should trigger violation
        with self.assertRaises(PolicyViolation):
            PolicyEngine.inspect_for_raw_secrets("DATABASE_URL=postgres://user:SecretPassword123!@localhost/db")

        # Abstract placeholder should pass cleanly
        try:
            PolicyEngine.inspect_for_raw_secrets("DATABASE_URL=<SECRET_REF_DATABASE_URL>")
        except PolicyViolation:
            self.fail("Secret placeholder unexpectedly raised PolicyViolation")

    def test_nginx_preconditions(self):
        # Missing syntax test passes raises PreconditionFailure
        with self.assertRaises(PreconditionFailure):
            PolicyEngine.verify_nginx_reload_preconditions({
                "nginx_configuration_valid": False,
                "backup_exists": True,
                "rollback_command_known": True
            })

        # All preconditions satisfied
        try:
            PolicyEngine.verify_nginx_reload_preconditions({
                "nginx_configuration_valid": True,
                "backup_exists": True,
                "rollback_command_known": True
            })
        except PreconditionFailure:
            self.fail("Valid preconditions unexpectedly failed")

class TestSecretMasking(unittest.TestCase):
    def setUp(self):
        self.masker = SecretMasker({
            "API_KEY": "sk_live_verysecretstring12345",
            "DB_PASS": "SuperSecurePass!"
        })

    def test_mask_and_resolve(self):
        raw_text = "Connect with sk_live_verysecretstring12345 to db"
        masked = self.masker.mask_text(raw_text)
        self.assertNotIn("sk_live_verysecretstring12345", masked)
        self.assertIn("<SECRET_REF_API_KEY>", masked)

        resolved = self.masker.resolve_references(masked)
        self.assertEqual(resolved, raw_text)

class TestToolContracts(unittest.TestCase):
    def setUp(self):
        self.harness = DeploymentHarness()

    def test_t0_worker_sizing(self):
        res = self.harness.tools.t0_calc_worker_sizing(cpu_cores=2, ram_gb=1.0)
        self.assertEqual(res["tier"], "T0")
        self.assertLessEqual(res["recommended_workers"], 3)

    def test_t4_nginx_reload(self):
        with self.assertRaises(PreconditionFailure):
            self.harness.tools.t4_reload_nginx({"nginx_configuration_valid": False})

        res = self.harness.tools.t4_reload_nginx({
            "nginx_configuration_valid": True,
            "backup_exists": True,
            "rollback_command_known": True
        })
        self.assertEqual(res["status"], "reloaded_cleanly")

    def test_t5_hitl_approval_required(self):
        # Purge backups without token must raise HumanApprovalRequired
        with self.assertRaises(HumanApprovalRequired):
            self.harness.tools.t5_purge_old_backups(retention_days=30)

        # With approval token, passes
        res = self.harness.tools.t5_purge_old_backups(retention_days=30, approval_token="APPROVE_PURGE_BACKUPS_30D")
        self.assertEqual(res["status"], "executed_with_human_authorization")

    def test_execution_budget(self):
        small_harness = DeploymentHarness(max_turns=2)
        small_harness.execute_plan_step("t1_inspect_service_status", {"service_name": "nginx"})
        small_harness.execute_plan_step("t1_inspect_service_status", {"service_name": "ssh"})
        with self.assertRaises(HarnessExecutionBudgetExceeded):
            small_harness.execute_plan_step("t1_inspect_service_status", {"service_name": "supervisor"})

if __name__ == "__main__":
    unittest.main()
