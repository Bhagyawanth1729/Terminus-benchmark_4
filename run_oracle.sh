#!/usr/bin/env bash
cd /workspace 2>/dev/null || cd "$(dirname "$0")"
harbor run -p tasks/timeseries-gorilla-compression -a oracle 2>&1 | tail -30
