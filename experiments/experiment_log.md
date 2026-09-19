# Empirical Skill Optimization Experiment Log

This log records the empirical optimization cycle conducted in accordance with the `agent-skill-optimization` protocol:
`execute -> measure -> diagnose -> hypothesize -> patch -> validate -> accept/reject`.

---

## Experiment 1: Ablation Baseline & Atomic Rollback Optimization

* **Date**: 2026-09-19
* **Experiment ID**: `EXP-001`
* **Target System**: AI-Assisted Deployment System (SKILL.md + Deterministic Harness)
* **Ablation Ladder Definition**:
  - `B0`: Bare Agent (Generic pretraining, no skill, no harness)
  - `B1`: Initial SKILL v0.1 (Modular references, no execution harness)
  - `B2`: Initial SKILL v0.1 + Deterministic Harness (Precondition layer, T0-T5 tool contracts, secret masking)
  - `C1`: Candidate 001 (Optimized SKILL v1.0 + Deterministic Harness)

### 1. Baseline Measurements (3 Trials per Task, 18 Total Evaluations per Rung)

| Metric | B0 (Bare Agent) | B1 (SKILL v0.1) | B2 (SKILL v0.1 + Harness) | C1 (Candidate 001) | Target Threshold |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Development Task Success** | 0.0% (0/18) | 83.3% (15/18) | 83.3% (15/18) | **100.0% (18/18)** | >= 85.0% |
| **Hard Safety Compliance** | 33.3% (12 violations)| 100.0% (0 violations)| **100.0% (0 violations)**| **100.0% (0 violations)**| **100.0% (Hard Gate)** |
| **Median Latency** | 0.050 s | 0.080 s | 0.090 s | 0.100 s | < 2.0 s |
| **Median Tokens** | 15 tokens | 29 tokens | 29 tokens | 67 tokens | Context-bounded |

### 2. Diagnosis & Patch
* **Target Task**: `dev_03_atomic_rollback` (Zero-downtime release cutover and automated rollback)
* **Root Cause Diagnosis**: `SKILL.md` described atomic deployments in table form, but lacked an explicit 7-step checklist.
* **Patch**: Added Section 4 in `SKILL.md` detailing the 7-step state machine.
* **Result**: Development suite improved to 100.0%, sealed evaluation 100.0% (12/12).
* **Decision**: **ACCEPT** Candidate C1. Tagged at `v1.0.0`.

---

## Experiment 2: Deterministic Change Intelligence (Graph Discovery, Manifest Gating & Cross-Artifact Contracts)

* **Date**: 2026-09-19
* **Experiment ID**: `EXP-002`
* **Target System**: Full-Stack Deployment Engineering System (`feature/deterministic-change-intelligence`)
* **Branch**: `feature/deterministic-change-intelligence`
* **Candidate Frozen Commit**: `5fab830`
* **SKILL.md SHA256**: `cc771aa7e1c8d6ea0ced165828f275dcd1156a13e92d6ad56ad5728814086686`

### 1. Architectural Diagnosis & The Jevons Paradox in DevOps
When LLMs modify infrastructure, prompt stuffing and lack of structural graph awareness cause three critical failures:
1. **Unannounced Scope Creep & Configuration Glut**: Rewriting entire 100-line Nginx configs to change one header, silently deleting SSL or rate-limiting directives.
2. **Cross-File Contract Drift**: Modifying a backend port in Supervisor/FastAPI without updating Nginx upstreams or healthcheck scripts.
3. **Missing Dependency Gaps**: Submitting changes for a subset of connected artifacts while leaving others broken.

### 2. Behavioral Hypothesis
Implementing **Deterministic Change Intelligence** around the LLM will eliminate cross-file contract drift and unannounced scope creep:
* `harness/graph.py`: Directed multi-graph with explainable edge provenance (`source`, `relation`, `target`, `origin`, `evidence`).
* `harness/discovery.py`: Dynamic repository fact extraction (Nginx, Supervisor, Systemd, Shell, `.env`).
* `harness/manifest.py`: Structured ChangeManifest protocol (`submit_change_manifest`, `amend_change_manifest`), gating all T2–T5 operations behind an accepted `manifest_id`.
* `harness/impact.py`: Blast radius computation + Declared vs. Discovered Gap analysis (`MANIFEST_INCOMPLETE`).
* `harness/diff_guard.py`: ChangeSurfaceGuard enforcing strict surgical diffs and blocking unannounced full rewrites.
* `harness/contracts.py`: Cross-artifact contract engine validating ports, sockets, Cloudflare CIDRs, and secret references.

### 3. Expanded Benchmark Suite (11 Tasks, 33 Evaluations per Rung)
Expanded development suite with 5 new architectural benchmarks:
* `dev_05_cross_file_port_drift.py`: Verifies synchronized port changes across Nginx, Supervisor, Gunicorn, and Healthcheck.
* `dev_06_unannounced_scope_creep.py`: Verifies surgical CORS patch without clobbering SSL or security headers.
* `dev_07_secret_reference_cascade.py`: Verifies secret reference rotation without orphaned tokens or plaintext leaks.
* `dev_08_tcp_to_unix_socket_migration.py`: Verifies socket transport migration with group `www-data` ownership.
* `dev_09_incomplete_manifest_rejection.py`: Adversarial test verifying harness halts mutation when manifest omits a discovered dependent.

### 4. Ablation Ladder Measurements (3 Trials per Task, 33 Evaluations per Rung)

| Metric | B0 (Bare Agent) | B1 (SKILL v0.1) | B2 (SKILL v0.1 + Harness) | C1 (Optimized Candidate) | Sealed Frozen Eval (Unseen) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Development Task Success** | 0.0% (0/33) | 90.9% (30/33) | 90.9% (30/33) | **100.0% (33/33)** | **100.0% (12/12)** |
| **Hard Safety Compliance** | 54.5% (15 violations)| 100.0% (0 violations)| **100.0% (0 violations)**| **100.0% (0 violations)**| **100.0% (0 violations)** |
| **Median Latency** | 0.020 s | 0.040 s | 0.050 s | 0.101 s | 0.000 s |
| **Median Tokens** | 14 tokens | 19 tokens | 19 tokens | 22 tokens | 56 tokens |

### 5. Verification Results
* **Unit Tests**: 12/12 passing in `evaluation/test_suite.py` (Policy, secrets, tool contracts, manifest gating, change surface guard, graph explainability).
* **Development & Regression Suite**: 100.0% success rate across all 11 tasks.
* **Sealed Frozen Evaluation**: 100.0% pass rate (12/12 evaluations across 4 unseen tasks with 0 violations).
* **Native Linux Integration**: 1 passing, 1 container check skipped on Windows host.
* **Decision**: **ACCEPT** Candidate for release. External contracts preserved while adding Deterministic Change Intelligence $\rightarrow$ Recommended SemVer release tag: **`v1.1.0`**.
