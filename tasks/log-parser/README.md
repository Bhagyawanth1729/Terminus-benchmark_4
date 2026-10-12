# Log Parser Task (Advanced)

## Difficulty explanation

This task tests the agent's ability to build a production-grade log parser that handles real-world complexities:

1. **Multiple log formats**: Structured key-value with nested JSON objects/arrays, plus multi-line entries (stack traces)
2. **Log rotation handling**: Files with `.1`, `.2` suffixes must be merged chronologically with base files
3. **Timestamp normalization**: 8+ timestamp formats (ISO 8601 with/without ms/µs, timezone offsets, space separators, slash dates, DD/MM/YYYY) all converted to UTC ISO 8601 with milliseconds
4. **Type inference**: Automatic detection of int, float, bool, JSON objects, JSON arrays, and strings
5. **Multi-line entry handling**: Stack traces and continued messages spanning multiple lines
6. **Deduplication**: Entries duplicated across rotated files must be deduplicated using composite keys (timestamp + level + message + request_id/job_id)
7. **Streaming/memory efficiency**: Large files (access.log) must be processed line-by-line without loading entirely into memory
8. **Dual output**: Structured parsed logs + aggregated statistics with computed metrics

The task is significantly harder than basic log parsing because:
- Real-world logs have inconsistent formats across sources
- Timezone handling is error-prone and often done incorrectly
- JSON parsing within key-value pairs requires careful bracket/brace counting
- Multi-line entries need stateful parsing
- Deduplication logic must match the exact composite key strategy
- Streaming requires generator-based architecture
- Aggregated statistics require single-pass computation

An experienced Python developer with log processing experience would take approximately 3 hours to implement a robust solution with proper error handling, streaming, and comprehensive test coverage.

## Solution explanation

The reference solution (`solution/parse_logs.py`) implements:

1. **LogParser class** with generator-based file processing for memory efficiency
2. **Flexible timestamp parsing** using `dateutil.parser` with fallback normalization for edge cases (slash dates, DD/MM/YYYY)
3. **Smart field parsing** that tracks bracket/brace depth to correctly split comma-separated key-value pairs containing JSON
4. **Type inference** with priority: JSON object/array → bool → int → float → string
5. **Stateful multi-line handling**: Continuation lines (indented) are appended to previous entry's message or stack_trace field
6. **Rotation-aware file ordering**: Groups files by base name, sorts as `.log.1` → `.log` → `.log.2` → `.log.3`...
7. **Composite-key deduplication**: Uses `(timestamp, level, message, request_id)` or `(timestamp, level, message, job_id)` when available
8. **Single-pass statistics**: Collects level counts, source counts, unique IDs, error codes, latencies, slow queries during parsing
9. **Dual JSON output**: Sorted parsed entries + comprehensive aggregated stats

Key implementation details:
- `parse_fields()` uses character-by-character parsing with depth tracking to handle nested JSON
- `normalize_timestamp()` handles 8+ formats, converts all to UTC ISO 8601 with 3-digit milliseconds
- `get_log_files_sorted()` implements rotation ordering logic
- Generator-based `process_file()` yields complete entries one at a time
- Statistics collected incrementally during parsing (no second pass needed)

## Verification explanation

The verification (`tests/test_parser.py`) checks 28 criteria across two test classes:

### Parsed Logs Tests (17 tests):
1. **Output existence & count**: 82 entries (70-85 expected range)
2. **Entry structure**: All required fields, valid levels, proper timestamp format
3. **Chronological ordering**: Entries sorted by normalized timestamp
4. **Type inference**: Int, float, bool, JSON object, JSON array detection
5. **JSON object parsing**: Nested metadata objects correctly parsed as dicts
6. **JSON array parsing**: Event arrays with mixed types correctly parsed as lists
7. **Stack trace preservation**: Multi-line stack traces preserved with newlines
8. **Rotated log processing**: Entries from `.1` files present and correctly ordered
9. **Deduplication**: Zero duplicates using composite keys
10. **Malformed line handling**: Skipped with stderr warnings
11. **Timestamp normalization**: All timestamps end in Z with 3-digit milliseconds
12. **Various timestamp formats**: All 10 timestamp.log entries parsed correctly
13. **All levels present**: INFO, ERROR, WARN, DEBUG, CRITICAL all represented
14. **Critical entry details**: Disk space critical with nested mounts array

### Aggregated Stats Tests (11 tests):
1. **Stats file existence**: Valid JSON with total_entries
2. **Level counts**: Match actual parsed data exactly
3. **Source counts**: All 7 log sources represented
4. **Time range**: Matches first/last entry timestamps
5. **Unique request IDs**: 25 unique request_ids counted
6. **Unique job IDs**: 2 unique job_ids (batch_001, batch_000)
7. **Unique user IDs**: 3 unique user_ids
8. **Error rate**: ERROR count / total = 0.09
9. **Avg latency**: Mean of all latency_ms fields = ~20.0ms
10. **Top errors**: DB_CONN_ERROR and PAYMENT_DECLINED ranked
11. **Slow queries**: q_456 with 5.2s duration captured

Tests run in separate verifier container with pytest, ensuring isolation.

## Relevant experience

This task is relevant for developers with experience in:
- **Log processing & observability** (DevOps, SRE, platform engineering)
- **Text parsing with complex grammars** (regex, state machines, recursive descent)
- **Timezone handling & timestamp normalization** (common source of bugs)
- **Streaming/iterator patterns** for memory-efficient large file processing
- **Data serialization** (JSON, nested structures)
- **Python ecosystem**: `dateutil`, `pathlib`, generators, `collections`
- **Real-world log formats**: syslog, structured logging, JSON logging, multi-line stacks

Similar production scenarios:
- Building log aggregation pipelines (ELK, Loki, Splunk ingestion)
- Parsing heterogeneous logs from microservices for centralized observability
- Converting legacy application logs to structured formats for analytics
- ETL pipelines processing TB-scale log data with rotation and deduplication
- Security log analysis requiring precise timestamp correlation across sources
- Compliance auditing needing complete, deduplicated log trails