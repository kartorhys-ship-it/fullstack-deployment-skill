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
from harness.manifest import ManifestRegistry, ChangeManifest, ManifestValidationError, ManifestStatus, canonicalize_path, PathTraversalViolation
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

        # Without a verified rollback checkpoint, T4 MUST fail precondition
        with self.assertRaises(PreconditionFailure):
            self.harness.tools.t4_reload_nginx(manifest_id=self.manifest.manifest_id)

        # Once a discrete state checkpoint is created, trusted probe passes
        self.harness.state.create_checkpoint("Pre-reload safety checkpoint", {})
        res = self.harness.tools.t4_reload_nginx(manifest_id=self.manifest.manifest_id)
        self.assertEqual(res["status"], "reloaded_cleanly")
        self.assertTrue(res.get("syntax_probed_ok"))

    def test_t4_supervisor_restart_preconditions(self):
        # Without manifest_id, T4 MUST fail
        with self.assertRaises(ToolContractError):
            self.harness.tools.t4_restart_supervisor("webapp")

        # Unknown/unverified service configuration must fail precondition
        with self.assertRaises(PreconditionFailure):
            self.harness.tools.t4_restart_supervisor("non_existent_service", manifest_id=self.manifest.manifest_id)

        # Without a verified rollback checkpoint, T4 MUST fail precondition
        with self.assertRaises(PreconditionFailure):
            self.harness.tools.t4_restart_supervisor("webapp", manifest_id=self.manifest.manifest_id)

        # With discrete checkpoint created and valid service in repository, restart succeeds
        self.harness.state.create_checkpoint("Pre-supervisor restart checkpoint", {})
        res = self.harness.tools.t4_restart_supervisor("webapp", manifest_id=self.manifest.manifest_id)
        self.assertEqual(res["status"], "restarted")
        self.assertTrue(res.get("service_probed_ok"))

    def test_gateway_manifest_amendment(self):
        """Tests agent capability gateway facade for transactional manifest amendments."""
        status = self.harness.gateway.get_manifest_status(self.manifest.manifest_id)
        self.assertEqual(status, ManifestStatus.ACCEPTED.value)

        amended = self.harness.gateway.amend_manifest(
            manifest_id=self.manifest.manifest_id,
            added_targets=["templates/nginx/security-headers.conf"],
            amendment_reason="Include security headers to active change scope"
        )
        self.assertEqual(amended.version, 2)
        self.assertIn("templates/nginx/security-headers.conf", amended.targets)
        self.assertEqual(amended.status, ManifestStatus.ACCEPTED)

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
        adversarial_paths = [
            "../etc/shadow",
            r"..\etc\shadow",
            "templates/../../etc/shadow",
            r"templates\..\..\etc\shadow",
            "/etc/shadow",
            r"\etc\shadow",
            r"C:\Windows\System32",
            "C:/Windows/System32",
            r"\\server\share\file",
            "//server/share/file",
            "",
            "   ",
            ".",
            "./",
        ]
        for bad_path in adversarial_paths:
            with self.subTest(bad_path=bad_path):
                with self.assertRaises(ManifestValidationError):
                    canonicalize_path(bad_path)

        # Valid relative paths normalized across separators
        self.assertEqual(canonicalize_path("./templates/nginx/app.conf"), "templates/nginx/app.conf")
        self.assertEqual(canonicalize_path(r"templates\nginx\app.conf"), "templates/nginx/app.conf")

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

    def test_cloudflare_real_ip_trust_contract(self):
        """Repository templates must satisfy complete Cloudflare proxy CIDRs and prohibited wildcards."""
        passed, reason = self.engine.verify_cloudflare_real_ip_trust()
        self.assertTrue(passed, f"verify_cloudflare_real_ip_trust failed: {reason}")


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

    def test_amendment_contract_failure_leaves_v1_intact(self):
        """End-to-end test: amending a manifest with a contract that fails verification rolls back candidate and preserves v1 ACCEPTED."""
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        harness = DeploymentHarness(repo_root=repo_root)

        # Initial manifest with valid invariants and complete blast radius succeeds
        m = harness.submit_change_manifest(
            intent="Base valid deployment",
            targets=[
                "templates/nginx/fullstack-app.conf",
                "templates/scripts/gunicorn_start.sh",
                "templates/supervisor/webapp.conf"
            ],
            expected_dependencies=["service:webapp"],
            invariants=["backend_port_consistency"],
            verification=["nginx_syntax"],
            rollback={"strategy": "none"}
        )
        self.assertEqual(m.version, 1)
        self.assertEqual(m.status, ManifestStatus.ACCEPTED)

        # Attempt to amend manifest by adding an unknown/violating invariant
        with self.assertRaises(ContractViolation) as ctx:
            harness.gateway.amend_manifest(
                manifest_id=m.manifest_id,
                added_targets=["templates/nginx/security-headers.conf"],
                added_invariants=["non_existent_violating_contract"],
                amendment_reason="Try to expand scope with bad invariant"
            )
        self.assertIn("non_existent_violating_contract", str(ctx.exception))

        # Original manifest remains intact at v1 and ACCEPTED
        orig = harness.manifest_registry.get_manifest(m.manifest_id)
        self.assertEqual(orig.version, 1)
        self.assertEqual(orig.status, ManifestStatus.ACCEPTED)
        self.assertEqual(len(orig.targets), 3)

        # Ensure staging area was discarded cleanly
        self.assertFalse(harness.manifest_registry.has_staged_amendment(m.manifest_id))
        self.assertIsNone(harness.manifest_registry.get_staged_amendment(m.manifest_id))
        self.assertFalse(harness.gateway.has_staged_amendment(m.manifest_id))

    def test_submission_unknown_contract_transitions_to_rejected(self):
        """Initial manifest submission with an unknown contract must raise UnknownContractError and transition to REJECTED."""
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        harness = DeploymentHarness(repo_root=repo_root)

        with self.assertRaises(UnknownContractError):
            harness.submit_change_manifest(
                intent="Deploy with unknown contract",
                targets=["templates/nginx/snippets/new-header.conf"],
                expected_dependencies=[],
                invariants=["unknown_bogus_contract_123"],
                verification=["nginx_syntax"],
                rollback={"strategy": "none"}
            )

        manifests = list(harness.manifest_registry._manifests.values())
        self.assertTrue(len(manifests) > 0)
        latest = manifests[-1]
        self.assertEqual(latest.status, ManifestStatus.REJECTED)
        self.assertIn("unknown_bogus_contract_123", latest.rejection_reason)


class TestT2ChangeSurfaceHardening(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.harness = DeploymentHarness(repo_root=self.repo_root)
        self.manifest = self.harness.submit_change_manifest(
            intent="T2 test deployment",
            targets=[
                "templates/nginx/fullstack-app.conf",
                "templates/scripts/gunicorn_start.sh",
                "templates/supervisor/webapp.conf"
            ],
            expected_dependencies=["service:webapp"],
            invariants=["backend_port_consistency"],
            verification=["nginx_syntax"],
            rollback={"strategy": "none"}
        )

    def test_t2_trusted_disk_blocks_ssl_deletion_spoof(self):
        """T2 must read real baseline from disk and detect deletion of SSL directives."""
        from pathlib import Path
        real_content = Path(self.repo_root, "templates/nginx/fullstack-app.conf").read_text(encoding="utf-8")
        # Delete ssl_certificate directives from proposal
        mutated = "\n".join([line for line in real_content.splitlines() if "ssl_certificate" not in line])

        with self.assertRaises(ChangeSurfaceViolation) as ctx:
            self.harness.execute_plan_step("t2_stage_config_patch", {
                "target_file": "templates/nginx/fullstack-app.conf",
                "new_content": mutated,
                "manifest_id": self.manifest.manifest_id
            })
        self.assertIn("deleted SSL certificate directives", str(ctx.exception))

    def test_t2_allows_legitimate_new_file_creation(self):
        """T2 allows creating authorized non-existent files with empty baseline."""
        new_target = "templates/nginx/snippets/new-header.conf"
        amended = self.harness.gateway.amend_manifest(
            manifest_id=self.manifest.manifest_id,
            added_targets=[new_target],
            amendment_reason="Authorize new header file"
        )
        res = self.harness.execute_plan_step("t2_stage_config_patch", {
            "target_file": new_target,
            "new_content": 'add_header X-Custom-Header "Active";\n',
            "manifest_id": amended.manifest_id
        })
        self.assertEqual(res["status"], "staged_validated")
        self.assertEqual(res["target_file"], new_target)
        self.assertIn('+add_header X-Custom-Header "Active";', res["diff"])

    def test_t2_blocks_path_escape(self):
        """T2 blocks target files that attempt traversal or escape repository root."""
        with self.assertRaises((ChangeSurfaceViolation, PathTraversalViolation)):
            self.harness.execute_plan_step("t2_stage_config_patch", {
                "target_file": "../etc/shadow",
                "new_content": "root:x:0:0:::",
                "manifest_id": self.manifest.manifest_id
            })


if __name__ == "__main__":
    unittest.main()

