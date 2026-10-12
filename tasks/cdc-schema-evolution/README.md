# CDC Schema Evolution Task

## Difficulty explanation

This task tests the agent's ability to correctly replay Change Data Capture (CDC) events while reconciling schema evolution — a critical real-world data engineering challenge. The core difficulties are:

1. **Schema mapping across versions**: Events from v1–v3 reference columns (`user_id`, `email` VARCHAR(50)) that don't exist in the target v4 schema (`customer_id`, `email` VARCHAR(200), `metadata` JSONB). The agent must build a column mapping from the schema history and apply it at event-application time, not after.

2. **Type coercion at the right moment**: A v1 INSERT may carry an email longer than 50 chars (the CDC captures the *attempted* value). The agent must respect the *source schema's* constraints when interpreting the event, not the target schema's.

3. **Default backfill gap**: The `metadata` JSONB column was added in v4 with `DEFAULT '{}'`. PostgreSQL does **not** backfill this default to existing rows. The agent must explicitly write `'{}'` for rows last updated in v1–v3 — a subtle trap that causes silent data corruption in production pipelines.

4. **DELETE/UPDATE semantics with schema changes**: An UPDATE from v2 only has `user_id` in its `after` image; the agent must merge this into a v4 row that has `customer_id`, preserving the existing `metadata` value.

5. **LSN ordering across files**: Events are split across 5 JSONL files but must be processed in global LSN order.

An experienced data engineer who has built CDC pipelines (Debezium, Kafka Connect, custom replication) would take ~4 hours to implement a robust solution with proper schema mapping, default handling, and Parquet output. The trap (default backfill) is the #1 cause of silent data corruption in real CDC schema migrations.

## Solution explanation

The reference solution (`solution/process_cdc.py`) implements:

1. **Schema-aware event mapping**: `_map_event_to_v4()` translates each event's `before`/`after` images from its source schema version to the v4 target schema using explicit rules derived from `schema_history.json`.

2. **Column mapping logic**:
   - v1–v2: `user_id` → `customer_id`
   - v1: `email` values truncated to 50 chars (source constraint)
   - v2+: `email` full length up to 200 chars
   - v1–v3: no `metadata` column → inject default `'{}'`
   - v4: `metadata` from event

3. **Stateful table reconstruction**: Maintains `table_state` dict keyed by `id` (PK). Processes events in LSN order:
   - INSERT: creates new row with all v4 columns + defaults
   - DELETE: removes row
   - UPDATE: merges only columns present in `after` image

4. **Default backfill**: `_ensure_v4_row()` explicitly sets `metadata = {}` for any row missing it, correctly handling the PostgreSQL "default not backfilled" behavior.

5. **Parquet output**: Uses pyarrow/pandas with explicit column ordering and types. Serializes `metadata` dict to JSON string. Parses ISO timestamps to datetime.

6. **Manifest generation**: Emits the exact transformation descriptions and column specifications required.

Key implementation details:
- Events loaded from all 5 JSONL files, sorted by `lsn` globally
- Generator-like processing (not fully streaming but memory-efficient for 5K events)
- Single-pass statistics collection during event application

## Verification explanation

The verification (`tests/test_processor.py`) runs in a separate verifier container with ground truth baked into the image:

### Parquet Tests (11 tests):
1. **Output existence**: `/app/output.parquet` exists
2. **Readability**: Parquet loads without error
3. **Column names & order**: Exactly `id, customer_id, email, status, created_at, metadata`
4. **PK uniqueness**: `id` column has no duplicates
5. **Row count match**: Agent output row count == ground truth (4222)
6. **Row-by-row value equality**: Every column compared against ground truth:
   - `created_at`: timestamp equality with timezone handling
   - `metadata`: JSON-parsed structural equality
   - `customer_id`: nullable integer handling (NaN/None)
   - Others: direct value comparison
7. **customer_id nullable**: Verifies NOT NULL drop in v3 produced nulls
8. **Email length ≤ 200**: VARCHAR(200) constraint respected
9. **Emails > 50 chars exist**: Confirms v2 widening was processed
10. **Metadata default backfill**: Many rows have `'{}'` (pre-v4 rows)
11. **Metadata structure for v4 rows**: Non-empty metadata has expected keys (`tier`, `features`, `last_login`)

### Manifest Tests (7 tests):
1. **Existence & valid JSON**
2. **Required fields present**: `source_table`, `target_schema_version`, `total_events_processed`, `transformations`, `row_count`, `columns`
3. **Source table = "users"**
4. **Target schema version = 4**
5. **Total events = 5000**
6. **Row count matches Parquet**
7. **Transformations array**: Exactly 3 entries with correct `from_version`, `to_version`, and `transform` strings for each migration
8. **Columns specification**: 6 columns with correct names, types, nullability, PK flags

### Event Processing Tests (4 tests):
1. **LSN ordering**: Events sorted by LSN before processing
2. **V1 email truncation**: Implicitly verified by row match
3. **V4 metadata backfill**: Explicitly checks >1000 rows with default
4. **DELETE/INSERT semantics**: Implicitly verified by row match

All tests are deterministic — ground truth was generated by the reference solution and baked into the verifier image. No network access, no randomness, no LLM-as-judge.

## Relevant experience

This task is directly relevant for professionals in:

- **Data Engineering / ETL / CDC Pipeline Development**: Building and maintaining database replication pipelines (Debezium, Kafka Connect, Airbyte, Fivetran, custom solutions)
- **Data Platform Engineering**: Schema evolution management in data warehouses/lakes
- **Database Administration**: Understanding `ALTER TABLE` semantics, default backfill behavior, replication internals
- **Streaming Data Systems**: Event sourcing, CQRS, materialized view maintenance

Real-world scenarios this task models:
- Migrating a CDC pipeline when upstream service changes its schema
- Replaying historical CDC events after a schema migration to backfill a data warehouse
- Debugging data discrepancies caused by schema evolution in replication
- Building a schema registry / compatibility checker for CDC
- Implementing "time travel" queries on CDC data with schema versions

Tools and concepts tested:
- JSON/JSONL parsing, Parquet I/O (pyarrow, pandas)
- Schema mapping, type coercion, nullable handling
- Event-driven state reconstruction
- PostgreSQL DDL semantics (`ALTER COLUMN TYPE`, `DROP NOT NULL`, `RENAME COLUMN`, `ADD COLUMN DEFAULT`)
- Deterministic data processing with audit trail (manifest)