# Engineering Contract — Demo

Companion repository to the article **"The Engineering Contract"**.

Shows the same refactoring task — splitting a 300-line FastAPI god-file into modular routers — run three ways:

| Directory | What it represents |
|---|---|
| `before/` | The original monolith — one file owns everything |
| `after-no-contract/` | Claude's output without an engineering contract |
| `after-with-contract/` | Claude's output following the engineering contract |

The two `CLAUDE.md` files at the root are the contracts used:

| File | Description |
|---|---|
| `CLAUDE.md` | The refined workspace contract — what produced the `after-with-contract` output |
| `CLAUDE.generic.md` | The generic starter from [engineering-guardrails-claude](https://github.com/ketan1602/engineering-guardrails-claude) |

---

## What to observe

### Bugs in `after-no-contract`

**Bug 1 — `/health` dropped**
The route exists in `before/main.py`. It does not appear in `after-no-contract/main.py` or any router file. It was silently lost during the split.

```bash
curl http://localhost:8000/health
# 404 Not Found
```

**Bug 2 — Route ordering: `/runs/pending` unreachable**
In `after-no-contract/routes/runs.py`, `/{run_id}` is registered before `/pending`. FastAPI matches `GET /runs/pending` against the parameterised route first, with `run_id="pending"`.

```bash
curl http://localhost:8000/runs/pending
# {"detail":"Run pending not found"}   ← should return the pending run list
```

**Bug 3 — Route ordering: `/models/default` unreachable**
Same pattern in `after-no-contract/routes/models.py`.

```bash
curl http://localhost:8000/models/default
# {"detail":"Model default not found"}  ← should return the default model
```

**Bug 4 — Duplicate status logic has drifted**
The `if/elif` status derivation chain exists in both `routes/runs.py` and `routes/results.py`, but with a subtle difference: `runs.py` handles `"completed_empty"`, `results.py` does not. They were the same in `before/main.py`. The split introduced a divergence.

### Fixes in `after-with-contract`

- All 13 routes present including `/health`
- `/runs/pending` registered before `/runs/{run_id}`
- `/models/default` registered before `/models/{model_id}`
- `derive_status()` extracted as a single function in `orm_models.py`, used by both `routes/runs.py` and `routes/results.py` — one source of truth

---

## Running each version

All three versions use the same dependencies. From within each directory:

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Interactive API docs: http://localhost:8000/docs

Each version writes a local SQLite database (`agentdb.db`) in the directory you run from. Delete it to reset state.

---

## Quick test sequence

```bash
# 1. Health check
curl http://localhost:8000/health

# 2. List models
curl http://localhost:8000/models
curl http://localhost:8000/models/default

# 3. Create a run
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"model_id": "claude-sonnet-4-6", "prompt": "summarise this document"}'

# 4. Pending runs (tests route ordering)
curl http://localhost:8000/runs/pending

# 5. Get a specific run
curl http://localhost:8000/runs/<run_id>
```

Run the same sequence against `after-no-contract` and `after-with-contract` to see the difference.

---

## Related

- [engineering-guardrails-claude](https://github.com/ketan1602/engineering-guardrails-claude) — the engineering contract repo this demo accompanies
