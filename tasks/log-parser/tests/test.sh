#!/bin/bash
set -e

# Create virtual environment and install test dependencies
uv venv /tmp/test-venv
source /tmp/test-venv/bin/activate
uv pip install pytest==9.1.1 pytest-json-ctrf==0.5.2

# Run the tests
python -m pytest test_parser.py -v --json-report --json-report-file=/tmp/test_results.json