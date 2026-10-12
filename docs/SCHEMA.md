# Task Schema Reference (Harbor format, Terminal-Bench style)

## 1. Folder layout
```
<task-slug>/
├── README.md          reviewer-facing explanations (4 required sections)
├── instruction.md     the prompt the agent sees
├── task.toml          config + metadata
├── environment/       AGENT image: Dockerfile + any data/code the agent should see
├── solution/          oracle: solve.sh (+ helper files). Never visible to agent
└── tests/             VERIFIER image: Dockerfile, test.sh, test files, ground truth
```
Rules: slug has at most 3 hyphen-separated tokens; the directory holds only files needed to
build, run, solve, or verify (no leftovers).

## 2. task.toml
```toml
# <canary comment, see section 6>
schema_version = "2.0"
artifacts = ["/app/output.json"]        # files/dirs the verifier reads from the agent container.
                                         # MUST be above the first [section]

[task]
name = "terminal-bench/<task-slug>"     # must equal org/<folder name>
description = ""
authors = [{ name = "...", email = "..." }]

[metadata]                               # only these keys are expected
author_name = ""                         # string or list
author_email = ""                        # string or list
author_organization = ""                 # optional
category = ""                            # one of 7 domains (section 5)
subcategory = ""                         # non-empty
tags = []
expert_time_estimate_hours = 0           # best case, focused expert
# optional: difficulty_explanation, solution_explanation, verification_explanation,
#           relevant_experience, referral

[verifier]
timeout_sec = 120.0                      # <= 18000
environment_mode = "separate"            # required: verifier runs in its own container
# optional: env, user, [verifier.environment], [[verifier.collect]]

[agent]
timeout_sec = 3600.0                     # positive integer-valued, <= 18000
# optional: user

[environment]
build_timeout_sec = 600.0
cpus = 1
memory_mb = 2048
storage_mb = 10240
gpus = 0                                 # max 1 (H100); add gpu_types = ["H100"] if gpus = 1
# allow_internet: OMIT this key. Open internet is the default; CI rejects both "= true" and "= false"
# optional: docker_image, env, skills_dir, mcp_servers, [environment.healthcheck]
```
Do not add invented fields; unknown keys are flagged. Leave the internet setting out entirely
(the benchmark default is open internet). Older docs mention `network_mode = "public"`; do not add it.

## 3. File-by-file rules

### instruction.md
- Written by you, concise, goal first, absolute paths (`/app/out.json`), explicit output format.
- If structured output is expected, document the exact schema in the instruction or a spec file.
- Tell the agent everything needed, nothing more; no step-by-step procedures (outcome-verified).
- Must end with a blank line and exactly:
  `You have N seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.`
  where N = `[agent].timeout_sec` as an integer.

### environment/Dockerfile (agent image)
- Do not pin apt package versions; run `apt-get update` first; end with `rm -rf /var/lib/apt/lists/*`.
- Never copy tests, solution, or ground truth into it.
- Pin pip/npm dependencies. Data lives in `environment/data/` and is copied with `COPY`.
- Files over 100 MB should not be committed (use a download script).
- Multi-container tasks: add `environment/docker-compose.yaml`.

### solution/solve.sh (oracle)
- `#!/bin/bash`, `set -euo pipefail`; Harbor mounts `solution/` at `/solution/`.
- Must actually compute the result (no hardcoded answers). Oracle must score 1.0.

### tests/
- `Dockerfile`: owns ALL verifier tooling (pytest, pytest-json-ctrf, uv, etc.), then `COPY . /tests/`
  and `mkdir -p` the parent dir of every declared artifact. Nothing is installed at verify time.
- `test.sh`: runs pytest with `--ctrf /logs/verifier/ctrf.json`, writes `1` or `0` into
  `/logs/verifier/reward.txt`.
- Ground truth / expected outputs live here, never in `environment/`.
- Verifier reads only: declared `artifacts`, files baked into the verifier image, or sidecar services.
- Tests are deterministic, check behavior by running things (not by grepping source), and every
  behavior in the instruction is tested and vice versa.

### README.md (reviewer-facing, 4 required `##` headings, 1-3 sentences each, human-written)
- `## Difficulty explanation`
- `## Solution explanation`
- `## Verification explanation`
- `## Relevant experience`

## 4. Static checks that run in CI (what `check_task.py` mirrors)
| Check | Rule |
|---|---|
| fields | metadata has author_name, author_email, category, subcategory, tags, expert_time_estimate_hours; README has the 4 sections |
| slug | at most 3 hyphen tokens |
| package name | `[task].name == "terminal-bench/<folder>"` |
| canary | canary string inside a comment in instruction.md, task.toml, environment/Dockerfile, solution/*, tests/* |
| instruction suffix | exact timeout sentence at the end |
| timeouts | agent and verifier timeout_sec <= 18000 |
| internet | `allow_internet` key must be absent (neither true nor false) |
| pytest pins | `pytest==9.1.1`, `pytest-json-ctrf==0.5.2` (the canonical versions in `reference/checks/check-pytest-version.sh`) |
| separate verifier | `environment_mode = "separate"`, tests/Dockerfile exists, tooling baked in |
| hygiene | pinned pip packages, apt cache cleanup, absolute paths |

## 5. Taxonomy (`category` is a closed set, `subcategory` is open)
- Science: Biology, Chemistry, Physics, Earth, Robotics, Math, Linguistics
- Software: Algorithms, Systems, Databases, Data engineering, Frontend, Languages
- ML: Training, Inference, Evaluation, Kernels
- Operations: Finance, Logistics, Supply chain, Claims, Compliance, Marketing
- Security: Cryptography, Reverse engineering, Forensics, AppSec
- Hardware: CAD, RTL
- Media: Music, Design
Classify by the primary skill exercised, not incidental tooling.

## 6. Canary
The benchmark requires its canary GUID inside a comment in task files so the data can be filtered from
training corpora. Keep the benchmark's own canary string exactly as in the template (it is a
benchmark-wide marker, not an author identifier). Markdown uses `<!-- ... -->`; other files use `#` or `//`.
