#!/bin/bash
set -e

echo "=== CDC Replay Schema Evolution - Starting ==="
cd /app

# Run the Python solution
python3 /app/solution/solve.py

echo "=== CDC Replay Schema Evolution - Complete ==="