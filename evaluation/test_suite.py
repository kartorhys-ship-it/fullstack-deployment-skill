"""Consolidated Unit and Integration Test Suite for Deterministic Change Intelligence.

Validates:
1. Harness core, policy engine, and secret masking
2. Tiered tool contracts (T0-T5) with mandatory manifest gating
3. Graph discovery with explainable edge provenance
4. Change manifest lifecycle & HITL invalidation upon amendment
5. Change surface guard & cross-artifact contract verifiers
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
from harness.manifest import ManifestRegistry, ChangeManifest, ManifestValidationError
from harness.diff_guard import ChangeSurfaceGuard, ChangeSurfaceViolation
from harness.contracts import CrossArtifactContractEngine


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

    def test_nginx_preconditions(self):
        with self.assertRaises(PreconditionFailure):
            PolicyEngine.verify_nginx_reload_preconditions({
                "nginx_configuration_valid": False,
                "backup_exists": True,
                "rollback_command_known": True
            })

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
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.harness = DeploymentHarness(repo_root=repo_root)
        # Register a valid baseline manifest for tool testing
        self.manifest = self.harness.manifest_registry.submit_manifest(
            intent="Test tool executions",
            targets=["templates/nginx/fullstack-app.conf"],
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
            self.harness.tools.t4_reload_nginx(
                {"nginx_configuration_valid": True, "backup_exists": True, "rollback_command_known": True}
            )

        # With manifest_id but failing precondition, raises PreconditionFailure
        with self.assertRaises(PreconditionFailure):
            self.harness.tools.t4_reload_nginx(
                {"nginx_configuration_valid": False},
                manifest_id=self.manifest.manifest_id
            )

        # With manifest_id and valid preconditions, passes
        res = self.harness.tools.t4_reload_nginx(
            {"nginx_configuration_valid": True, "backup_exists": True, "rollback_command_known": True},
            manifest_id=self.manifest.manifest_id
        )
        self.assertEqual(res["status"], "reloaded_cleanly")

    def test_t5_hitl_approval_required(self):
        # Purge backups without approval raises HumanApprovalRequired
        with self.assertRaises(HumanApprovalRequired):
            self.harness.tools.t5_purge_old_backups(
                retention_days=30,
                manifest_id=self.manifest.manifest_id
            )

        # Authorize HITL
        self.harness.tools.authorize_t5_action("APPROVE_PURGE_BACKUPS_30D", manifest_id=self.manifest.manifest_id)
        res = self.harness.tools.t5_purge_old_backups(
            retention_days=30,
            manifest_id=self.manifest.manifest_id,
            approval_token="APPROVE_PURGE_BACKUPS_30D"
        )
        self.assertEqual(res["status"], "executed_with_human_authorization")

    def test_execution_budget(self):
        small_harness = DeploymentHarness(max_turns=2)
        small_harness.execute_plan_step("t1_inspect_service_status", {"service_name": "nginx"})
        small_harness.execute_plan_step("t1_inspect_service_status", {"service_name": "ssh"})
        with self.assertRaises(HarnessExecutionBudgetExceeded):
            small_harness.execute_plan_step("t1_inspect_service_status", {"service_name": "supervisor"})


class TestDeterministicChangeIntelligence(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.graph = discover_repository(self.repo_root)

    def test_graph_discovery_explainability(self):
        """Every discovered edge must possess complete explainable evidence."""
        self.assertGreater(len(self.graph.edges), 0)
        for edge in self.graph.edges:
            self.assertIn(edge.origin, ("discovered", "declared"))
            self.assertIsNotNone(edge.evidence)
            self.assertTrue(bool(edge.evidence.file))
            self.assertGreater(edge.evidence.line, 0)
            self.assertTrue(bool(edge.evidence.extractor))

            explanation = edge.explain()
            self.assertIn(edge.source, explanation)
            self.assertIn(edge.target, explanation)

    def test_change_surface_guard_unexpected_file(self):
        """Guard must reject mutation of files not declared in manifest targets."""
        registry = ManifestRegistry()
        manifest = registry.submit_manifest(
            intent="Update Nginx CORS",
            targets=["templates/nginx/fullstack-app.conf"],
            expected_dependencies=[],
            invariants=["nginx_configuration_must_validate"],
            verification=["nginx_syntax"],
            rollback={"strategy": "none"}
        )

        guard = ChangeSurfaceGuard(manifest)
        # Attempting to edit supervisor config must fail
        allowed, reason = guard.validate_mutation(
            target_file="templates/supervisor/webapp.conf",
            original_content="[program:webapp]\ncommand=gunicorn",
            new_content="[program:webapp]\ncommand=uvicorn"
        )
        self.assertFalse(allowed)
        self.assertIn("CHANGE_SURFACE_VIOLATION", reason)

    def test_change_surface_guard_unannounced_rewrite(self):
        """Guard must reject unannounced full-file rewrites when full_rewrite=False."""
        registry = ManifestRegistry()
        manifest = registry.submit_manifest(
            intent="Surgical header update",
            targets=["templates/nginx/fullstack-app.conf"],
            expected_dependencies=[],
            invariants=["nginx_configuration_must_validate"],
            verification=["nginx_syntax"],
            rollback={"strategy": "none"},
            full_rewrite=False
        )

        guard = ChangeSurfaceGuard(manifest)
        orig_content = "line\n" * 50
        completely_different = "totally different content\n" * 10

        allowed, reason = guard.validate_mutation(
            target_file="templates/nginx/fullstack-app.conf",
            original_content=orig_content,
            new_content=completely_different
        )
        self.assertFalse(allowed)
        self.assertIn("Unannounced full-file rewrite", reason)

    def test_amendment_invalidates_hitl_approval(self):
        """CRITICAL INVARIANT: Manifest amendment must revoke prior HITL approvals."""
        registry = ManifestRegistry()
        manifest = registry.submit_manifest(
            intent="Purge backups",
            targets=["templates/scripts/clean_backups.sh"],
            expected_dependencies=[],
            invariants=["backup_retention_policy"],
            verification=["dry_run"],
            rollback={"strategy": "none"}
        )

        # Grant HITL
        registry.grant_hitl_approval(manifest.manifest_id)
        self.assertTrue(manifest.hitl_approved)

        # Amend manifest with new target
        registry.amend_manifest(
            manifest_id=manifest.manifest_id,
            new_targets=["templates/systemd/meilisearch.service"],
            amendment_reason="Also need to update Meilisearch service unit"
        )

        # HITL approval MUST be invalidated
        self.assertFalse(manifest.hitl_approved)
        self.assertEqual(manifest.version, 2)


if __name__ == "__main__":
    unittest.main()
