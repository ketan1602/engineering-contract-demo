# Engineering Guardrails — The Engineering Contract

These rules apply to every project and every session. Follow them unconditionally.
When asked to design, refactor, or implement anything, verify compliance before responding.

**Adopt at the right level:**
- **Lightweight** — §1–5 + §10–12. Solo projects, small teams, getting started.
- **Standard** — All sections. Production software, professional teams.
- **Regulated** — All sections + `adoption/regulated-profile.md`. Compliance-sensitive environments.
- **Stack-specific** — Extend with a file from `examples/`.

---

## 1. Functionality Preservation

**Never drop existing behaviour during a refactor.**

- Before splitting a file, list every public name it exports (classes, functions, constants, routes).
- After splitting, verify every name is re-exported from a shim or package `__init__.py`.
- Route ordering must be preserved: specific paths before parameterised ones (e.g. `/queue/pending` before `/{job_id}`).
- Backward-compat re-exports are mandatory when a module moves to a package.
- When in doubt, run an explicit cross-check: for each original import statement, confirm the resolved module still contains the symbol.

---

## 2. File Size — hard limit 150 lines (excluding blank lines and comments)

**No file may exceed 150 non-blank, non-comment lines.**

- Count before committing to a design. If a class alone exceeds 150 lines, it violates SRP — split it.
- Config files that are purely data (YAML, SQL, TOML) are exempt; logic files are not.
- Acceptable split strategies:
  - Extract a sub-package with an `__init__.py` re-exporting everything the original file exported.
  - Extract a mixin or base class for shared transport/plumbing.
  - Extract pure-data or pure-helper modules (schema, defaults, constants).
- Shim files (`from x import *`) count as 1–5 lines and are encouraged.

---

## 3. SOLID Principles

### Single Responsibility (SRP)
Each file owns one concern: one route group, one adapter, one handler, one reporter.
God-classes (files that import from 6+ modules and define 5+ public names) must be split.

### Open/Closed (OCP)
Prefer a registry or dispatch table over `if/elif` chains.
- New variants add a file and a registry entry — never a branch in an existing function.
- Example: `@register_adapter("name")` decorator; `_DISPATCH = {"type": module.run}`.

### Liskov Substitution (LSP)
All implementations of the same role must share an identical public signature.
Use `**_` to absorb unused kwargs so callers always pass the full set without breaking substitution.

### Interface Segregation (ISP)
Split transport from domain methods. Callers import only what they need.
Example: `_ClientBase` owns `_request()`; `DomainClient(_ClientBase)` owns domain methods.

### Dependency Inversion (DIP)
Feature flags and backing-service availability checks live at the call site, not buried in utilities.

### Interface Ergonomics
- Call methods on direct collaborators only. `a.b.c.do()` is a coupling violation — add a delegation method on `a` instead.
- Names, defaults, and return values should match what a reasonable developer expects. Surprising behaviour is a design defect; rename or restructure before explaining.

---

## 4. 12-Factor App

### Factor III — Config
- **No hardcoded URLs, credentials, or default service addresses in source code.**
- Every backing-service address comes from an env var; missing = loud error, not silent fallback.
- Secrets never appear in YAML, code, or log output — only via env vars or secret stores.

### Factor VI — Processes
- Stateless, idempotent startup operations only (e.g. seed scripts use `ON CONFLICT DO UPDATE`).
- Never write state to the local filesystem between requests; use the backing store.

### Factor XI — Observability
- Structured JSON logs. No bare `print()` in application code.
- Levels: `info` for normal, `warning` for degraded paths, `error` for failures.
- Never log secrets, passwords, or tokens at any level.
- Propagate a `trace_id` and `span_id` across every service hop; include both in every log line.
- Emit counters for key operations started/completed/failed, and operation latency.
- Every service exposes a `/health` endpoint: liveness = process up, readiness = dependencies reachable.

---

## 5. Simplicity — YAGNI, KISS, DRY

- Prefer the simpler solution. Complexity is a choice; usually the wrong one.
- Solve the stated problem only. Do not design for hypothetical future requirements.
- One authoritative source for each piece of knowledge; duplication leads to divergence.
- In tests, some repetition is fine when it aids readability — don't abstract shared setup until ≥ 3 tests need it.
- Leave every file slightly cleaner than you found it. Fix one small thing per touch.
- A helper is justified only when called from ≥ 3 distinct call sites.
- No half-finished implementations; no feature flags for things that don't exist yet.
- No error handling for scenarios that cannot happen; trust internal contracts.
- Functions with > 7 branching keywords (`if`, `elif`, `for`, `while`, `except`, `and`, `or`) must be split.
- Replace branching on type/key with a dispatch dict or registry.

---

## 6. Error Handling

- Validate inputs at system boundaries (user input, external APIs); surface errors immediately rather than letting bad state propagate.
- Only recover from an exception if you can handle it meaningfully; otherwise re-raise.
- Always log caught exceptions with enough context to reproduce (type, message, relevant IDs).
- Never swallow exceptions silently — especially in `async` loops where failures disappear without a trace.

---

## 7. Secrets Management

**Secrets must never be hardcoded — not even as "changeme" placeholder defaults.**

### How secrets are injected (in order of preference)
1. **Secret Manager** (e.g. HashiCorp Vault, AWS Secrets Manager, Azure Key Vault) — injects as env vars at runtime.
2. **`.env` file** — developer-local only. Gitignored. Never committed. Always provide `.env.example` with empty placeholders.
3. **k8s secretKeyRef** — for secrets bound to pod env vars in Helm values.

### Rules
- Source `.env` at startup if it exists — this is a local-developer convenience, not a substitute for a secret manager.
- After sourcing, validate every required secret; fail loudly if absent. Never run silently with an empty secret.
- **No CLI `--password` flags as the primary mechanism.** A flag may exist as a last-resort override but must never be the documented workflow.
- Never log secrets, tokens, or passwords at any level (even DEBUG).
- Never pass secrets via URL query params or in request bodies that get logged.
- k8s manifests and Helm charts must use `secretKeyRef` for all secrets — never `value:`.

### Shell script pattern
```bash
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"; [[ "$SCRIPT_DIR" == "${BASH_SOURCE[0]}" ]] && SCRIPT_DIR="."

if [[ -f "${SCRIPT_DIR}/.env" ]]; then source "${SCRIPT_DIR}/.env"; fi

MY_SECRET="${MY_SECRET_ENV_VAR:-}"
: "${MY_SECRET:?MY_SECRET_ENV_VAR must be set (see .env.example)}"
```

---

## 8. Config-Driven Infrastructure

Infrastructure components are selected at runtime via env var — never hardcoded in code or config files.

- A named env var selects the component (e.g. `INFRA_BROKER=rabbitmq`); credentials are injected as separate env vars.
- All implementations of the same role share an identical interface — swapping a component means changing config, not code (LSP + OCP).
- Common swappable layers: message broker, cache, container registry, service mesh, relational DB, graph DB, vector store.
- See `rules/agentic-systems.md` for a full open-source / cloud-native component matrix.

---

## 9. Deploy Workflow

Choose a track based on target environment. Full steps belong in your project's `deploy.sh` or CI pipeline.

| Track | Mode | Registry | Cluster |
|---|---|---|---|
| 0 | Local, no container | — | — |
| 1 | Container, local Kubernetes | Private registry | Local cluster (minikube / kind / OrbStack) |
| 2 | Container, Azure | ACR | AKS |
| 3 | Container, AWS | ECR | EKS |

Pre-built upstream images (GHCR, Docker Hub): pull + retag, then follow Track 1/2/3 from the login step. Verify registry reachability before attempting a pull — corporate firewalls commonly block public registries.

**Universal rules:**
- Registry passwords via stdin only — never as CLI arguments.
- `KUBE_CONTEXT` env var selects the cluster — same script, any target.
- Idempotent applies: `--dry-run=client -o yaml | kubectl apply -f -` for secrets and configmaps.
- Every Deployment pulling from a private registry must declare `imagePullSecrets`.

---

## 10. Change Workflow

Before implementing any non-trivial change, follow in order:

1. Restate the intended outcome in one sentence.
2. Inspect all relevant files before modifying any of them.
3. Identify existing patterns; reuse them before introducing new ones.
4. For changes spanning more than one file, produce a short implementation plan.
5. Make the smallest coherent change that satisfies the requirement.
6. Run tests, linting, and type checks; do not claim success without evidence.
7. Review the diff for unintended modifications before reporting done.
8. State what was validated and what risks or limitations remain.

---

## 11. Escalation Conditions

Stop and present options rather than proceeding autonomously when:

- Requirements conflict or are ambiguous.
- The change requires a breaking API, schema, or interface change.
- A database migration could cause data loss or is irreversible.
- The task modifies a security boundary, authentication, or authorization model.
- The requested implementation conflicts with an existing architectural decision.
- Several materially different designs are viable and the choice has significant consequences.
- Required credentials, dependencies, schemas, or source files are absent.
- The change would affect production infrastructure.
- Validation cannot be completed in the available environment.

---

## 12. Definition of Done

A task is not complete until all of the following are true:

- The requested behaviour is implemented.
- Existing behaviour remains compatible unless a breaking change was explicitly authorized.
- Tests cover the new or changed behaviour and have been executed.
- Static analysis, type checks, and formatting checks pass.
- Error and edge cases are handled.
- No secrets, tokens, or sensitive data appear in code, config, or logs.
- Operational telemetry is added where the change affects observable system behaviour.
- The response states what was validated and identifies any known limitations.
