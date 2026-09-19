# AI-Assisted Deployment System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Ubuntu LTS](https://img.shields.io/badge/Platform-Ubuntu%2024.04%20%7C%2022.04%20LTS-orange.svg)]()
[![Architecture: LLM Proposes, Determinism Enforces](https://img.shields.io/badge/Architecture-Harness--Enforced-blue.svg)]()

A robust, testable AI-assisted DevOps framework and modular agent skill for automated full-stack deployments on Ubuntu Linux with Nginx, Gunicorn/FastAPI, Node.js/Vite, Meilisearch, Cloudflare CDN, and GitHub Actions CI/CD.

Derived from the 10.4-hour course *"How to Deploy, Secure, and Automate Full-Stack Web Apps"* by Imad Saddik / freeCodeCamp.org, this repository pairs deep production operational knowledge with an **AI Harness Architecture** and an **Empirical Skill Optimization** benchmark suite.

---

## Architectural Principle: The LLM Proposes, Determinism Enforces

In this system, the model is treated as fallible and untrusted:
1. **Agentic Layer (LLM + Skill)**: Formulates deployment blueprints, analyzes runtime errors (e.g. 502 Bad Gateway, OOM killer), and prepares configuration changes using abstract secret references (`<SECRET_REF_*>`).
2. **Deterministic Harness Layer**:
   - Enforces tiered tool contracts (T0–T5) with an explicit Human-in-the-Loop (HITL) gate on destructive/lockout actions.
   - Evaluates hard safety preconditions before allowing any state-changing execution.
   - Restores real visitor IP trust boundaries and verifies dynamic CSP nonces.
   - Manages state checkpoints and initiates atomic rollback upon health check failure.
3. **Dual Verification**: Fast Layer A simulation sandbox for iterative testing, plus Layer B native Linux container integration verifying real system binaries (`nginx -t`, `sshd -t`, `visudo -cf`, `systemd-analyze verify`).

---

## Repository Structure Overview

- `SKILL.md`: Root orchestrator skill routing agent to specialized domain references.
- `provenance/`: Upstream source tracking, licensing audit, and Ubuntu 24.04/22.04 version compatibility matrix.
- `references/`: Deep modular documentation across security, runtime, proxy, data, deployment, and operations.
- `templates/`: Audited configuration files and production shell scripts.
- `harness/`: Python implementation of deterministic policy engine, T0–T5 tools, secret masking, and state checkpoints.
- `sandbox/`: Fast Layer A simulation and behavioral HTTP verifier.
- `integration/`: Layer B native Linux validation container and test scripts.
- `benchmarks/`: Public benchmark partitions (`development/` and `regression/`).
- `sealed_evaluator/`: Isolated evaluation suite for final unsealed validation.
- `experiments/`: Ablation ladder runs (B0, B1, B2, C1) and empirical optimization records.
