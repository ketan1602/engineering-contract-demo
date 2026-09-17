# Engineering Guardrails — Global

These rules apply to every project and every session. Follow them unconditionally.
When asked to design, refactor, or implement anything, verify compliance before responding.

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
  - Extract a sub-package (`foo/` with `__init__.py` re-exporting everything `foo.py` used to).
  - Extract a mixin or base class for shared transport/plumbing.
  - Extract pure-data or pure-helper modules (schema, defaults, assets, cells).
- Shim files (`from x import *`) count as 1–5 lines and are encouraged.

---

## 3. SOLID Principles

### Single Responsibility (SRP)
Each file owns one concern: one route group, one adapter, one handler, one reporter.
God-classes (files that import from 6+ modules and define 5+ public names) must be split.

### Open/Closed (OCP)
Prefer a registry or dispatch table over `if/elif` chains.
- New variants add a file and a registry entry — never a branch in an existing function.
- Example: `@register_adapter("Name")` decorator; `_DISPATCH = {"type": module.run}`.

### Liskov Substitution (LSP)
All implementations of the same role must share an identical public signature.
Use `**_` to absorb unused kwargs so callers always pass the full set without breaking substitution.

### Interface Segregation (ISP)
Split transport from domain methods. Callers import only what they need.
Example: `_ClientBase` owns `_request()`; `ApiClient(_ClientBase)` owns domain methods.

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
- Structured JSON logs (e.g. `structlog`). No bare `print()` in application code.
- Levels: `info` for normal, `warning` for degraded paths, `error` for failures.
- Never log secrets, passwords, or tokens at any level.
- Propagate a `trace_id` and `span_id` across every service hop; include both in every log line.
- Emit counters for agent steps started/completed/failed, and tool call latency — these are the signals that page someone.
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
- Never swallow exceptions silently — especially in `async` agent loops where failures disappear without a trace.

---

## 7. Secrets Management

**Secrets must never be hardcoded — not even as "changeme" placeholder defaults.**

### How secrets are injected (in order of preference)
1. **Vault Agent** — injects secrets as env vars at pod startup (CI and production).
2. **`.env` file** — developer-local only. Gitignored. Never committed. Always provide a `.env.example` with empty placeholder values documenting every required secret.
3. **k8s secretKeyRef** — for secrets bound to pod env vars in Helm values.

### Rules
- Deploy scripts must `source .env` at startup if the file exists; this is _not_ a substitute for Vault — it is a local-developer convenience.
- After sourcing, validate every required secret with `die` if absent. Never silently run with an empty or default secret.
- **No CLI `--password` flags as the primary mechanism.** A flag may exist as a last-resort override but must never be the documented workflow — that trains developers to type secrets into shell history.
- Never log secrets, tokens, or passwords at any level (even DEBUG).
- Never pass secrets via URL query params or in request bodies that get logged.
- k8s manifests and Helm charts must use `secretKeyRef` for all secrets — never `value:`.

### Shell script pattern
```bash
# Fork-free SCRIPT_DIR — never use $(cd "$(dirname ...)") which spawns two subshells
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"; [[ "$SCRIPT_DIR" == "${BASH_SOURCE[0]}" ]] && SCRIPT_DIR="."

# Source local .env (gitignored — never committed)
if [[ -f "${SCRIPT_DIR}/.env" ]]; then source "${SCRIPT_DIR}/.env"; fi

# Apply env var overrides (Vault injects these in CI)
MY_SECRET="${MY_SECRET_ENV_VAR:-}"

# Validate — die loudly if missing
: "${MY_SECRET:?MY_SECRET_ENV_VAR must be set (see .env.example)}"
```

---

## 8. Config-Driven Infrastructure

Infrastructure components are selected at runtime via env var — never hardcoded in code or config files.

- `INFRA_BROKER`, `INFRA_CACHE`, `INFRA_REGISTRY`, etc. select the component; credentials are injected as separate env vars.
- All implementations of the same role share an identical interface — swapping a component means changing config, not code (LSP + OCP).
- Supported components per layer (open-source, Azure, AWS): see `~/.claude/AGENTIC_STACK.md`.

---

## 9. UI Framework Standard

All operator-facing web UIs across this workspace follow one consistent pattern. Do not introduce React, Vue, Next.js, or any JS build toolchain unless the user explicitly requests it.

### Stack
- **Backend:** FastAPI — modular routers, one file per concern under `api/routes/`.
- **Frontend:** Vanilla JS + static HTML/CSS — no bundler, no framework, no node_modules.
- **Streaming:** SSE (`EventSource` in JS, `StreamingResponse(media_type="text/event-stream")` in FastAPI) for live agent/pipeline output.
- **Data:** REST JSON for all non-streaming operations.

### File layout (canonical)
```
api/
├── main.py            # FastAPI app — mounts routes + serves static/
├── routes/
│   ├── health.py      # GET /health
│   ├── <concern>.py   # one router per domain (runs, events, results …)
│   └── ...
└── static/
    ├── index.html     # single page — no server-side templating
    ├── app.js         # all interactivity, fetches /api/v1/...
    └── styles.css     # CSS variables only — no utility classes
```

### Design system (shared across all projects)
Dark-theme CSS variables — use these names verbatim so UIs are visually consistent:
```css
:root {
  --bg:       #0f1117;
  --surface:  #1a1d27;
  --border:   #2a2d3a;
  --text:     #e2e8f0;
  --muted:    #6b7280;
  --accent:   #6366f1;   /* primary action / highlight */
  --success:  #22c55e;
  --warning:  #f59e0b;
  --error:    #ef4444;
}
```

### Rules
- `index.html` is served by FastAPI via `StaticFiles(directory="static", html=True)` — no Jinja2.
- No authentication middleware unless the user explicitly asks for it.
- Streaming endpoints use SSE; the JS side opens an `EventSource` and appends chunks.
- CSS is hand-authored against the variables above — no Tailwind, Bootstrap, or other utility libraries.
- Each FastAPI router is a separate file; all are imported in `api/main.py` — never one god-file.

### Reference implementations
- `llm-perf-harness`: SSE streaming pattern, Prometheus `/metrics`, modular routes.
- `agent-bench`: HITL interactive flows, queue-based routing, same CSS vocabulary.

---

## 10. Deploy Workflow

Choose a track based on target environment. Full steps in `~/.claude/DEPLOY.md`.

| Track | Mode | Registry | Cluster |
|---|---|---|---|
| 0 | Local, no container | — | — |
| 1 | Container, local K8s | Harbor / `localhost:5000` | OrbStack / minikube / kind |
| 2 | Container, Azure | ACR | AKS |
| 3 | Container, AWS | ECR | EKS |

Pre-built upstream images (GHCR, Docker Hub): pull + retag, then follow Track 1/2/3 from the login step. Verify registry reachability first — corporate firewalls commonly block ghcr.io.

**Universal rules:**
- Passwords via stdin only — never as CLI arguments.
- `KUBE_CONTEXT` env var selects the cluster — same script, any target.
- Idempotent applies: `--dry-run=client -o yaml | kubectl apply -f -` for secrets/configmaps.
- Every Deployment pulling from a registry must have `imagePullSecrets`.

---

## 11. Change Workflow

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

## 12. Escalation Conditions

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

## 13. Definition of Done

A task is not complete until all of the following are true:

- The requested behaviour is implemented.
- Existing behaviour remains compatible unless a breaking change was explicitly authorized.
- Tests cover the new or changed behaviour and have been executed.
- Static analysis, type checks, and formatting checks pass.
- Error and edge cases are handled.
- No secrets, tokens, or sensitive data appear in code, config, or logs.
- Operational telemetry is added where the change affects observable system behaviour.
- The response states what was validated and identifies any known limitations.
