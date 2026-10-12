# Terminal-Bench Task Starter Kit

A clean, name-free starter for writing your own Terminal-Bench (Harbor format) task.

## Contents
- `docs/SCHEMA.md`      folder layout, every `task.toml` field, README sections, CI rules, taxonomy
- `docs/CHECKLIST.md`   pre-submission checklist
- `task-template/my-task/`  copy this folder, rename it, fill the `TODO`s
- `check_task.py`       quick all-in-one structural checker (mirrors the main CI rules)
- `reference/`          sanitized copies of the original tooling:
  - `checks/`   the 24 static check scripts (`check-*.sh`), `rubric_review.py`, `check-ai-detection.py`, and `test-tasks/` fixtures. **Use these.**
  - `rubrics/`  task proposal rubric, implementation rubric (28 criteria), trial-analysis rubrics. **Read these and use them for self-review.**
  - `scripts/`  maintainer release tooling (not needed to write a task)
  - `tools/`    maintainer/reviewer tooling (deep-review, fortify, rubric_regression, trial-costs, diagrams). Optional.

## Quick start
1. `cp -r task-template/my-task tasks/<your-slug>` (max 3 hyphen-separated words)
2. Edit `task.toml`: `[task].name = "terminal-bench/<your-slug>"`, your metadata, timeouts.
3. Write `instruction.md` yourself; keep the required last sentence matching `[agent].timeout_sec`.
4. Build `environment/`, `solution/solve.sh`, `tests/`.
5. Run every static check from the folder that contains `tasks/`:
   `for c in reference/checks/check-*.sh; do bash "$c" tasks/<your-slug>; done`
6. `harbor run -p tasks/<your-slug> -a oracle` (must give reward 1.0)

## What was sanitized in `reference/`
Upstream GitHub org/repo names, community chat and website URLs, third-party repo links, and
internal skill paths are replaced with placeholders such as `<ORG>` and `<YOUR_BENCH_REPO>`.
Lockfiles are removed. No contributor names or real emails remain (fixtures use `test@example.com`).
Tools that reference those placeholders (fortify, deep-review, trial-costs, release script) need
you to fill them in before they work; they are not needed to author a task.
Kept on purpose: the benchmark canary GUID, the `terminal-bench` org default in
`check-task-package-name.sh` (edit `ORG=` if you publish elsewhere), and Claude/Anthropic model names.
Licence: the original repository is Apache-2.0; keep its notice if you redistribute these copied files.
