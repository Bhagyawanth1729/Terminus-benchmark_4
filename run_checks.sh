#!/usr/bin/env bash
for f in terminal-bench-4.0.0/checks/check-*.sh; do
  echo "=== $f ==="
  bash "$f" "tasks/timeseries-gorilla-compression" 2>&1 | tail -5
  echo "exit:$?"
done
