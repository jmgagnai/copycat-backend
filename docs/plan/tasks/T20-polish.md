# T20 — Polish: README, tooling, type checks, cleanup (dropped)

| Mode | Effort | Priority | Depends on | Unblocks | Learning value |
| --- | --- | --- | --- | --- | --- |
| Drop | 0 | — | — | — | — |

## Why it is dropped

Housekeeping with no Python learning. Do the two items that cost minutes when you get to them;
skip the rest.

## Worth two minutes each, when convenient

### 1. Lint and type-check configuration

In `pyproject.toml`:

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
ignore = ["B008"]           # `Depends()` in a parameter default is FastAPI's idiom

[tool.pyright]
typeCheckingMode = "basic"  # already set
venvPath = "."
venv = ".venv"              # so third-party types resolve
```

### 2. A "run" section in the README

Five commands, in the order a newcomer needs them, plus one line on what the stack expects:

| Command | What it does |
| --- | --- |
| `uv sync` | install the dependencies into `.venv` |
| `cp .env.example .env` | then fill in the keys |
| `uv run python main.py` | start the server on port 3000 |
| `uv run pytest` | run the test suite |
| `docker compose up -d` (in NOTEBOOKS) | Postgres, MinIO, and the Docling image the converter pulls |

Write it by running the commands in a fresh shell and pasting what worked.

## If you pick it up later

| Item | What to do |
| --- | --- |
| Leftover files | `pyoas.yaml` at the repository root is unused now that the DTOs are hand-maintained: remove it, or document the regeneration command if you keep generating them. `src/main.py` and `src/generated` are already gone. |
| pre-commit | Enable the commented-out `pytest` hook in `.pre-commit-config.yaml` if the suite stays fast. |
| Administrator restore | Confirm `ADMIN_EMAILS` restore works end to end with curl (NOTEBOOKS `docs/administration.md`). |
| README: simplifications | List the deliberate differences from the Node backend, so nobody files them as bugs (see below). |

The deliberate simplifications versus the Node backend:

- no retry of a failed ingestion (T14);
- no per-section summaries, no corrective rewrite (T12);
- no keyword search (T17, T18);
- LLM failures reported as `unexpected`;
- the failed status written on every attempt, not only the last.

### What you would need to know

- **ruff.** `uv run ruff check src test --fix` and `uv run ruff format src test`. The rule sets:
  `E` pycodestyle, `F` pyflakes, `I` import order, `B` bugbear, `UP` pyupgrade.
- **pyright in `basic` mode** finds wrong attribute names and `None` misuse. `venvPath` and
  `venv` point it at `.venv` so third-party types resolve. The pre-commit hook runs `pyrefly`,
  which reads the same `[tool.pyright]` section.
- **pre-commit.** `uv run pre-commit install` once; the hooks then run on every `git commit`.
- **A README "run" section** is five commands. Write it by running them in a fresh shell and
  pasting.
