# Log Parser Task (Advanced)

You are given a directory `/app/logs` containing multiple log files in various formats. Your task is to write a Python script that parses ALL log files, handles complex formats, and produces structured JSON outputs at `/app/parsed_logs.json` and `/app/aggregated_stats.json`.

## Log Formats

### Format 1: Structured Key-Value (Primary)
```
[LEVEL] TIMESTAMP - MESSAGE - KEY1=VALUE1, KEY2=VALUE2, ...
```

Values can be:
- **Simple types**: integers, floats, strings
- **JSON objects**: `metadata={"device": "mobile", "os": "iOS"}`
- **JSON arrays**: `events=[{"type": "click", "ts": "..."}, ...]`
- **Mixed**: `tags=["api", "user"], metadata={"endpoint": "/api/users"}`

### Format 2: Multi-line Entries
Some log entries span multiple lines (stack traces, continued messages):
```
[ERROR] 2024-01-15T11:01:30Z - Batch job failed - job_id=batch_001, error=OutOfMemoryError, stack_trace="java.lang.OutOfMemoryError: Java heap space\n\tat com.app.BatchProcessor.process(BatchProcessor.java:142)\n\tat com.app.BatchProcessor.run(BatchProcessor.java:89)"
```

Continuation lines (indented or without timestamp) belong to the previous entry.

### Format 3: Log Rotation
Files with numeric suffixes (`.1`, `.2`, etc.) are rotated logs that must be merged chronologically with their base file. Process in order: `app.log.1` → `app.log` → `app.log.2` (if exists).

### Format 4: Timestamp Variations
Handle these timestamp formats:
- `2024-01-15T10:30:45Z` (ISO 8601 UTC)
- `2024-01-15T10:30:45.123Z` (with milliseconds)
- `2024-01-15T10:30:45.123456Z` (with microseconds)
- `2024-01-15T10:30:45+00:00` (explicit UTC offset)
- `2024-01-15T10:30:45-05:00` (timezone offset)
- `2024-01-15 10:30:45` (space separator)
- `2024/01/15 10:30:45` (slash date)
- `15/01/2024 10:30:45` (DD/MM/YYYY)

Convert all to UTC ISO 8601 with milliseconds: `2024-01-15T10:30:45.123Z`

## Requirements

### 1. Parse ALL `.log` and `.log.*` files in `/app/logs/`
- Include rotated logs (`.1`, `.2`, etc.)
- Process rotated logs in correct chronological order
- Handle empty files gracefully

### 2. Extract Structured Fields
For each log entry, extract:
- `level`: Log level (INFO, ERROR, WARN, DEBUG, CRITICAL)
- `timestamp`: Normalized to UTC ISO 8601 with milliseconds (`YYYY-MM-DDTHH:MM:SS.mmmZ`)
- `message`: Descriptive message
- `fields`: Dictionary with **properly typed values**:
  - Integers: `user_id=12345` → `12345` (int)
  - Floats: `memory_percent=87.5` → `87.5` (float)
  - Booleans: `auth_present=true` → `true` (bool)
  - JSON objects: `metadata={"key": "val"}` → `{"key": "val"}` (dict)
  - JSON arrays: `events=[...]` → `[...]` (list)
  - Strings: everything else (including escaped JSON strings in stack_trace)

### 3. Handle Multi-line Entries
- Stack traces and continued messages (lines starting with whitespace or `\t`)
- Merge continuation lines into the `message` or appropriate field
- Preserve newlines in stack_trace fields

### 4. Deduplication
- Some log entries may be duplicated across rotated files
- Deduplicate by `(timestamp, level, message, request_id)` or `(timestamp, level, message, job_id)` when available
- Keep the first occurrence (from earliest rotated file)

### 5. Streaming / Memory Efficiency
- The `access.log` file is large (simulated) — process line-by-line
- Do NOT load entire files into memory
- Use generators/iterators for parsing

### 6. Output 1: `/app/parsed_logs.json`
JSON array of ALL parsed entries (after deduplication), sorted by timestamp:
```json
[
  {
    "level": "INFO",
    "timestamp": "2024-01-15T10:25:00.000Z",
    "message": "Service starting",
    "fields": {
      "version": "1.2.3",
      "pid": 1234
    }
  }
]
```

### 7. Output 2: `/app/aggregated_stats.json`
JSON object with aggregated statistics:
```json
{
  "total_entries": 150,
  "by_level": {"INFO": 80, "ERROR": 15, "WARN": 10, "DEBUG": 30, "CRITICAL": 5},
  "by_source": {"app.log": 20, "app.log.1": 10, "service.log": 9, "api.log": 16, "access.log": 20, "timestamps.log": 10},
  "time_range": {"start": "2024-01-15T10:25:00.000Z", "end": "2024-01-15T12:01:25.000Z"},
  "unique_request_ids": 35,
  "unique_job_ids": 2,
  "unique_user_ids": 5,
  "error_rate": 0.1,
  "avg_latency_ms": 23.5,
  "top_errors": [{"error_code": "DB_CONN_ERROR", "count": 3}, {"error_code": "PAYMENT_DECLINED", "count": 2}],
  "slow_queries": [{"query_id": "q_456", "duration_s": 5.2}, ...]
}
```

### 8. Handle Edge Cases
- Malformed lines → skip with warning to stderr
- Missing fields section → empty `fields` dict
- Invalid JSON in fields → treat as string
- Duplicate entries across rotated files → deduplicate
- Large files → stream, don't load entirely

## Files
- Input logs: `/app/logs/*.log` and `/app/logs/*.log.*`
- Output 1: `/app/parsed_logs.json`
- Output 2: `/app/aggregated_stats.json`
- Your solution script: `/app/solve.sh` (should run your Python parser)

## Verification
Your solution will be verified by running tests that check:
- All log files processed (including rotated)
- Correct chronological ordering
- Timestamp normalization to UTC ISO 8601 with ms
- Proper type inference (int, float, bool, dict, list, string)
- Multi-line entry handling (stack traces)
- Deduplication across rotated files
- Memory-efficient streaming for large files
- Both output files valid and complete
- Aggregated statistics correctness

You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.