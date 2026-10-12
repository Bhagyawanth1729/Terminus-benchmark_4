# Pre-submission checklist

Task quality
- [ ] Real work someone would be paid to do on a computer
- [ ] Hard for a good reason (expert skill / long horizon / rich environment), not volume or trivia
- [ ] Solvable by an expert in a few hours; oracle demonstrates it
- [ ] Not an unsolved research problem; not easily found online
- [ ] Novel: not a rehash of an existing public benchmark task

Spec and verifier
- [ ] Instruction is short, goal-first, absolute paths, exact output schema if structured
- [ ] Every tested behavior is in the instruction, every instructed behavior is tested
- [ ] Outcome-verified (no "use tool X" rules); deterministic; re-running 100x never flakes
- [ ] Tests execute behavior, not grep source; anti-cheat for editable test/config files
- [ ] Ground truth only in tests/, never in environment/

Files
- [ ] task.toml has only valid fields; `[task].name` = `terminal-bench/<folder>`
- [ ] Canary comment in every required file; instruction ends with the timeout sentence
- [ ] Agent image clean; verifier image has all tooling; pinned deps; apt cache cleaned
- [ ] README has the 4 required sections, written by you
- [ ] No leftover files; no typos in paths and filenames

Runs
- [ ] `python check_task.py <task>` passes
- [ ] `harbor run -p <task> -a oracle` gives 1.0
- [ ] A no-op agent gives 0.0
- [ ] A strong model attempt analyzed: why does it fail (genuine difficulty, not misspecification)?
