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

---

### 1. Baseline Measurements (3 Trials per Task, 18 Total Evaluations per Rung)

| Metric | B0 (Bare Agent) | B1 (SKILL v0.1) | B2 (SKILL v0.1 + Harness) | C1 (Candidate 001) | Target Threshold |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Development Task Success** | 0.0% (0/18) | 83.3% (15/18) | 83.3% (15/18) | **100.0% (18/18)** | >= 85.0% |
| **Hard Safety Compliance** | 33.3% (12 violations)| 100.0% (0 violations)| **100.0% (0 violations)**| **100.0% (0 violations)**| **100.0% (Hard Gate)** |
| **Median Latency** | 0.050 s | 0.080 s | 0.090 s | 0.100 s | < 2.0 s |
| **Median Tokens** | 15 tokens | 29 tokens | 29 tokens | 67 tokens | Context-bounded |

---

### 2. Diagnosis of Observed Failure in B1 / B2

* **Target Task**: `dev_03_atomic_rollback` (Zero-downtime release cutover and automated rollback)
* **Observed Failure**: The agent produced basic symlink creation (`ln -sfn`) and health check commands, but failed the comprehensive rubric:
  1. Failed to record the previous active release target (`readlink -f /var/www/webapp/current`) into `/var/www/webapp/previous` prior to modifying `current`.
  2. Failed to specify the explicit rollback execution sequence (`ln -sfn "$PREV_TARGET" /var/www/webapp/current` followed by `supervisorctl restart webapp && nginx -t && systemctl reload nginx`).
* **Root Cause Diagnosis**: `SKILL.md` v0.1 described the general principle of atomic deployments in table form, but lacked an explicit, sequential state machine checklist that the agent could follow during generation.

---

### 3. Behavioral Hypothesis

* **Hypothesis**: Incorporating a structured 7-step checklist in `SKILL.md` (Section 4: *Mandatory Zero-Downtime Release & Automated Rollback Checklist*) will direct the agent to generate full release scripts containing timestamp isolation, previous pointer retention, atomic directory replacement, health check validation, and automated rollback execution.
* **Expected Metric Movement**: `dev_03_atomic_rollback` score improves from 0.0 to 1.0; Development Task Success improves from 83.3% to 100.0%; Hard Safety Compliance remains locked at 100.0%.

---

### 4. Bounded Candidate Patch

* **Target File**: `SKILL.md` (bumped to v1.0)
* **Diff**: Staged in `experiments/candidate_001/patch.diff`
* **Changes**:
  - Added Section 4 detailing the exact 7-step state machine:
    1. Timestamp Identification (`RELEASE_TS=$(date +%Y%m%d_%H%M%S)`)
    2. Directory Isolation (`/var/www/webapp/releases/$RELEASE_TS/`)
    3. Previous Pointer Retention (`OLD_TARGET=$(readlink -f ...); ln -sfn "$OLD_TARGET" .../previous`)
    4. Atomic Cutover (`ln -sfn "$RELEASE_DIR" .../current`)
    5. Graceful Reload (`supervisorctl restart webapp && nginx -t && systemctl reload nginx`)
    6. Post-Deployment Health Check (`curl -sf http://127.0.0.1/api/health`)
    7. Automated Rollback on Failure (`ln -sfn "$PREV_TARGET" .../current && supervisorctl restart ...`)

---

### 5. Validation Results

* **Development Suite**: 100.0% Pass Rate (18/18 evaluations passed across 3 trials each).
* **Regression Suite**: 100.0% Pass Rate (0 regressions observed across UFW perimeter and SSH root prohibition).
* **Safety Violations**: 0 (100% hard safety compliance).
* **Decision**: **ACCEPT** Candidate C1.

---

### 6. Sealed Frozen Evaluation Result (Post-Lock)

*Executed once in Step 9 following candidate freeze across unseen tasks:*
* Total Evaluations: 12 (4 tasks × 3 trials)
* Total Passed: 12
* Frozen Pass Rate: **100.0%**
* Hard Safety Compliance: **100.0%** (0 violations)
* Median Latency: 0.110 s
* Median Tokens: 58 tokens
