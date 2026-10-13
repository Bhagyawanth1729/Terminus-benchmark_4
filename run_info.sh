#!/usr/bin/env bash
ls terminal-bench-4.0.0/tools || true
ls terminal-bench-4.0.0/scripts || true
find terminal-bench-4.0.0 -maxdepth 2 -name "check_task.py" || true
ls terminal-bench-4.0.0/tasks | head -30
