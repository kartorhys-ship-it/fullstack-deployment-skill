"""Consolidated Unit and Integration Test Suite for Hardened Deterministic Change Intelligence.

Validates:
1. Policy engine, secret masking, and execution budgets
2. Tiered tool contracts (T0-T5) gated by transactional ACCEPTED manifests
3. Trusted out-of-band HITL approvals (no self-authorization on tool surface)
4. Independent precondition probes (observed host facts, not caller booleans)
5. Canonical exact path matching (no substring bleed)
6. Fail-closed contract engine (UnknownContractError)
7. Transactional manifest amendments with automatic rollback on validation failure
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from harness.policy import PolicyEngine, PolicyViolation, PreconditionFailure
from harness.secrets import SecretMasker
from harness.state import StateManager
from harness.tools import DeploymentTools, HumanApprovalRequired, ToolContractError
from harness.core import DeploymentHarness, HarnessExecutionBudgetExceeded
from harness.graph import DeploymentDependencyGraph, EdgeEvidence
from harness.discovery import discover_repository
from harness.manifest import ManifestRegistry, ChangeManifest, ManifestValidationError, ManifestStatus, canonicalize_path
from harness.diff_guard import ChangeSurfaceGuard, ChangeSurfaceViolation
from harness.contracts import CrossArtifactContractEngine, ContractViolation, UnknownContractError
from harness.approvals import TrustedApprovalService


class TestPolicyEngine(unittest.TestCase):
    def test_prohibited_commands(self):
        with self.assertRaises(PolicyViolation):
            PolicyEngine.validate_command_safety("rm -rf /")

        with self.assertRaises(PolicyViolation):
            PolicyEngine.validate_command_safety("rm -rf /var/www/webapp")

        with self.assertRaises(PolicyViolation):
            PolicyEngine.validate_command_safety("chmod 777 /var/www/webapp/shared")

    def test_secret_detection(self):
        with self.assertRaises(PolicyViolation):
            PolicyEngine.inspect_for_raw_secrets("DATABASE_URL=postgres://user:SecretPassword123!@localhost/db")

        try:
            PolicyEngine.inspect_for_raw_secrets("DATABASE_URL=<SECRET_REF_DATABASE_URL>")
        except PolicyViolation:
            self.fail("Secret placeholder unexpectedly raised PolicyViolation")


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


class TestHardenedToolContracts(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.harness = DeploymentHarness(repo_root=self.repo_root)
        # Submit valid manifest (transitions to ACCEPTED state)
        self.manifest = self.harness.submit_change_manifest(
            intent="Test tool executions",
            targets=[
                "templates/nginx/fullstack-app.conf",
                "templates/scripts/gunicorn_start.sh",
                "templates/supervisor/webapp.conf"
            ],
            expected_dependencies=["service:webapp"],
            invariants=["nginx_configuration_must_validate"],
            verification=["nginx_syntax"],
            rollback={"strategy": "restore_backup"}
        )

    def test_t0_worker_sizing(self):
        res = self.harness.tools.t0_calc_worker_sizing(cpu_cores=2, ram_gb=1.0)
        self.assertEqual(res["tier"], "T0")
        self.assertLessEqual(res["recommended_workers"], 3)

    def test_t4_nginx_reload_manifest_gating(self):
        # Without manifest_id, T4 MUST fail
        with self.assertRaises(ToolContractError):
            self.harness.tools.t4_reload_nginx()

        # With accepted manifest_id, trusted probe runs syntax check and passes
        res = self.harness.tools.t4_reload_nginx(manifest_id=self.manifest.manifest_id)
        self.assertEqual(res["status"], "reloaded_cleanly")
        self.assertTrue(res.get("syntax_probed_ok"))

    def test_t5_trusted_hitl_authorization(self):
        # T5 without out-of-band human approval MUST raise HumanApprovalRequired
        with self.assertRaises(HumanApprovalRequired):
            self.harness.tools.t5_purge_old_backups(
                retention_days=30,
                manifest_id=self.manifest.manifest_id
            )

        # Grant trusted out-of-band approval via ApprovalService with exact arguments
        self.harness.approval_service.grant_approval(
            manifest_id=self.manifest.manifest_id,
            manifest_version=self.manifest.version,
            action="purge_backups",
            operator_identity="sec_ops_admin@corp.internal",
            arguments={"retention_days": 30}
        )

        res = self.harness.tools.t5_purge_old_backups(
            retention_days=30,
            manifest_id=self.manifest.manifest_id
        )
        self.assertEqual(res["status"], "executed_with_human_authorization")

    def test_parameter_substitution_rejected(self):
        """Operator approves retention_days=90, agent calls with retention_days=1 -> MUST BE BLOCKED."""
        self.harness.approval_service.grant_approval(
            manifest_id=self.manifest.manifest_id,
            manifest_version=self.manifest.version,
            action="purge_backups",
            operator_identity="sec_ops_admin@corp.internal",
            arguments={"retention_days": 90}
        )

        with self.assertRaises(HumanApprovalRequired) as ctx:
            self.harness.tools.t5_purge_old_backups(
                retention_days=1,
                manifest_id=self.manifest.manifest_id
            )
        self.assertIn("PARAMETER_SUBSTITUTION_DETECTED", str(ctx.exception))

    def test_agent_tool_gateway_execution(self):
        """Verifies that AgentToolGateway executes tools safely through harness enforcement."""
        res = self.harness.gateway.execute_tool("t0_calc_worker_sizing", cpu_cores=2, ram_gb=1.0)
        self.assertEqual(res["tier"], "T0")

    def test_failed_contract_raises_violation_in_plan_step(self):
        """Executing T4 when a contract fails MUST raise ContractViolation before execution."""
        bad_manifest = self.harness.manifest_registry.create_pending_manifest(
            intent="Test bad contract gate",
            targets=["templates/nginx/fullstack-app.conf"],
            expected_dependencies=[],
            invariants=["unknown_violating_contract"],
            verification=["check_syntax"],
            rollback={"strategy": "none"}
        )
        self.harness.manifest_registry.accept_manifest(bad_manifest.manifest_id)

        with self.assertRaises(ContractViolation):
            self.harness.execute_plan_step("t4_reload_nginx", {"manifest_id": bad_manifest.manifest_id})

    def test_amendment_invalidates_prior_hitl_authorization(self):
        """CRITICAL INVARIANT: Prior approval granted for v1 must fail if manifest is amended to v2."""
        # Grant approval for v1
        self.harness.approval_service.grant_approval(
            manifest_id=self.manifest.manifest_id,
            manifest_version=self.manifest.version,
            action="purge_backups",
            operator_identity="sec_ops_admin@corp.internal",
            arguments={"retention_days": 30}
        )

        # Amend manifest to version 2
        amended = self.harness.amend_change_manifest(
            manifest_id=self.manifest.manifest_id,
            new_targets=["templates/nginx/security-headers.conf"],
            amendment_reason="Expand scope to include security headers"
        )
        self.assertEqual(amended.version, 2)

        # Calling T5 with v1 approval MUST be rejected!
        with self.assertRaises(HumanApprovalRequired) as ctx:
            self.harness.tools.t5_purge_old_backups(
                retention_days=30,
                manifest_id=self.manifest.manifest_id
            )
        self.assertIn("Approval version mismatch", str(ctx.exception))


class TestCanonicalPathAndChangeSurface(unittest.TestCase):
    def setUp(self):
        self.registry = ManifestRegistry()
        self.manifest = self.registry.create_pending_manifest(
            intent="Update Nginx CORS",
            targets=["templates/nginx/fullstack-app.conf"],
            expected_dependencies=["service:webapp"],
            invariants=["nginx_configuration_must_validate"],
            verification=["nginx_syntax"],
            rollback={"strategy": "none"}
        )
        self.registry.accept_manifest(self.manifest.manifest_id)

    def test_canonicalize_path_rejects_traversal(self):
        with self.assertRaises(ManifestValidationError):
            canonicalize_path("../etc/shadow")

        with self.assertRaises(ManifestValidationError):
            canonicalize_path("/var/log/nginx")

        self.assertEqual(canonicalize_path("./templates/nginx/app.conf"), "templates/nginx/app.conf")

    def test_exact_path_matching_blocks_sibling_files(self):
        """Declaring 'templates/nginx/fullstack-app.conf' must NOT authorize 'templates/nginx/security-headers.conf'."""
        guard = ChangeSurfaceGuard(self.manifest)
        allowed, reason = guard.validate_mutation(
            target_file="templates/nginx/security-headers.conf",
            original_content="add_header X-Frame-Options DENY;",
            new_content="add_header X-Frame-Options SAMEORIGIN;"
        )
        self.assertFalse(allowed)
        self.assertIn("CHANGE_SURFACE_VIOLATION", reason)


class TestFailClosedContracts(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.engine = CrossArtifactContractEngine(self.repo_root)

    def test_unknown_contract_fails_closed(self):
        """Unknown invariant must raise UnknownContractError, NOT pass silently."""
        with self.assertRaises(UnknownContractError):
            self.engine.verify_contract("non_existent_magic_contract")

    def test_backup_retention_policy_passes_on_templates(self):
        """clean_backups.sh specifies RETENTION_DAYS=30 >= 7, which must pass."""
        passed, reason = self.engine.verify_backup_retention_policy()
        self.assertTrue(passed, f"verify_backup_retention_policy failed: {reason}")

    def test_swap_memory_guard_contract(self):
        """Repository templates must satisfy swap memory security invariants."""
        passed, reason = self.engine.verify_swap_memory_guard()
        self.assertTrue(passed, f"verify_swap_memory_guard failed: {reason}")


class TestDiscoveryHealth(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    def test_discovery_health_records_progress(self):
        graph = discover_repository(self.repo_root)
        self.assertIsNotNone(graph.health)
        self.assertGreater(graph.health.files_discovered, 0)
        self.assertGreater(graph.health.files_parsed, 0)
        self.assertTrue(graph.health.is_healthy)

    def test_discovery_failure_blocks_target_manifest(self):
        from harness.impact import ImpactAnalyzer
        graph = discover_repository(self.repo_root)
        # Inject simulated parse failure for a declared target
        graph.health.parse_failures.append({
            "file": "templates/nginx/corrupted.conf",
            "error": "Syntax error on line 12",
            "extractor": "nginx"
        })
        analyzer = ImpactAnalyzer(graph)
        manifest = ChangeManifest(
            manifest_id="chg_test_parse_fail",
            version=1,
            intent="Test corrupt file",
            targets=["templates/nginx/corrupted.conf"],
            expected_dependencies=[],
            invariants=[],
            verification=["nginx_syntax"],
            rollback={"strategy": "none"}
        )
        passed, err = analyzer.verify_manifest_impact(manifest)
        self.assertFalse(passed)
        self.assertIn("discovery_parse_failures", str(err))


class TestTransactionalManifestState(unittest.TestCase):
    def setUp(self):
        self.registry = ManifestRegistry()

    def test_lifecycle_pending_to_accepted(self):
        m = self.registry.create_pending_manifest(
            intent="Test",
            targets=["templates/nginx/fullstack-app.conf"],
            expected_dependencies=[],
            invariants=["nginx_configuration_must_validate"],
            verification=["nginx_syntax"],
            rollback={"strategy": "none"}
        )
        self.assertEqual(m.status, ManifestStatus.PENDING_VALIDATION)
        self.assertFalse(m.is_accepted)

        self.registry.accept_manifest(m.manifest_id)
        self.assertEqual(m.status, ManifestStatus.ACCEPTED)
        self.assertTrue(m.is_accepted)

    def test_amendment_rollback_leaves_original_intact(self):
        m = self.registry.create_pending_manifest(
            intent="Test",
            targets=["templates/nginx/fullstack-app.conf"],
            expected_dependencies=[],
            invariants=["nginx_configuration_must_validate"],
            verification=["nginx_syntax"],
            rollback={"strategy": "none"}
        )
        self.registry.accept_manifest(m.manifest_id)

        # Stage amendment candidate
        candidate = self.registry.stage_amendment(
            manifest_id=m.manifest_id,
            new_targets=["templates/supervisor/webapp.conf"],
            amendment_reason="Add supervisor"
        )
        self.assertEqual(candidate.status, ManifestStatus.AMENDING)

        # Simulate validation failure -> rollback
        self.registry.rollback_amendment(m.manifest_id, "Impact check failed")

        # Original manifest remains intact at v1 and ACCEPTED!
        orig = self.registry.get_manifest(m.manifest_id)
        self.assertEqual(orig.version, 1)
        self.assertEqual(orig.status, ManifestStatus.ACCEPTED)
        self.assertEqual(orig.targets, ["templates/nginx/fullstack-app.conf"])


if __name__ == "__main__":
    unittest.main()
