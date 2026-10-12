FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-dateutil \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for CDC replay
RUN pip install --no-cache-dir \
    fastavro==1.9.0 \
    pyarrow==16.1.0 \
    duckdb==1.0.0 \
    python-dateutil==2.9.0.post0

# Copy data files into the image (data will be mounted at runtime, but copy for build-time reference)
COPY environment/data/ /app/data/

# Copy solution
COPY solution/ /app/solution/

# Create output directory
RUN mkdir -p /app/output

# Copy entry point
COPY environment/solve.sh /app/solve.sh
RUN chmod +x /app/solve.sh

ENTRYPOINT ["/app/solve.sh"]