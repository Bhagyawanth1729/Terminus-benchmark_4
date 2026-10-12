FROM python:3.11-slim

WORKDIR /app

# Install python3-dateutil for timestamp parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-dateutil \
    && rm -rf /var/lib/apt/lists/*

# Copy the log files into the image
COPY logs/ /app/logs/

# Copy parser and entry point
COPY parse_logs.py /app/parse_logs.py
COPY solve.sh /app/solve.sh
RUN chmod +x /app/solve.sh

ENTRYPOINT ["/app/solve.sh"]