# T20 — Polish: README, tooling, type checks, cleanup (dropped)

| Mode | Effort | Priority | Depends on | Unblocks | Learning value |
| --- | --- | --- | --- | --- | --- |
| Drop | 0 | — | — | — | — |

## Why it is dropped

Housekeeping with no Python learning. Do the two items that cost minutes when you get to them;
skip the rest.

## Worth two minutes each, when convenient

- `pyproject.toml`: ruff rules `E, F, I, B, UP` (ignore `B008`), pyright pointed at the venv
  (`venvPath = "."`, `venv = ".venv"`), `basic` mode.
- Five lines in the README: `uv sync`, `.env`, `uv run python main.py`, `uv run pytest`, and
  which compose services and Docling image it expects.

## If you pick it up later

- Remove `src/main.py` (the experiment script), `pyoas.yaml` and `src/generated` references if
  DTOs are now hand-maintained; otherwise document the regeneration command.
- Enable the `pytest` hook in `.pre-commit-config.yaml` if the suite stays fast.
- Confirm `ADMIN_EMAILS` restore works end to end with curl (NOTEBOOKS `docs/administration.md`).
- Note the deliberate simplifications versus the Node backend in the README: no retry, no
  per-section summaries, no keyword search, LLM failures reported as `unexpected`, failed status
  written on every attempt.

### What you would need to know

- ruff: `uv run ruff check src test --fix` and `uv run ruff format src test`; the rule sets `E`
  (pycodestyle), `F` (pyflakes), `I` (import order), `B` (bugbear), `UP` (pyupgrade).
- pyright `basic` mode finds wrong attribute names and `None` misuse; `venvPath`/`venv` in
  `pyproject.toml` point it at `.venv` so third-party types resolve.
- pre-commit: `uv run pre-commit install` once; hooks run on `git commit`.
- A README "run" section is five commands; write it by running them in a fresh shell and pasting.
