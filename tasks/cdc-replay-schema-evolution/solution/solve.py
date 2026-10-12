#!/usr/bin/env python3
"""
CDC Replay with Schema Evolution Solution

This script processes CDC events from a simulated Kafka topic, applies schema transformations
to match the current Snowflake target schema, and outputs Parquet files.
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Set, Tuple

import fastavro
import pyarrow as pa
import pyarrow.parquet as pq

# Set high precision for decimal operations
getcontext().prec = 38

# Constants
DATA_DIR = "/app/data"
SCHEMAS_DIR = os.path.join(DATA_DIR, "schemas")
EVENTS_DIR = os.path.join(DATA_DIR, "events")
TARGET_SCHEMA_FILE = os.path.join(DATA_DIR, "target_schema.sql")
OUTPUT_DIR = "/app/output"

# Tables in target schema (from instruction.md)
TARGET_TABLES = [
    "customers",
    "products",
    "orders",
    "order_items",
    "payments",
    "refunds",
    "order_adjustments",
    "inventory",
    "shipping",
    "audit_log",
]

# Numeric columns that need precision padding from scale 2 to scale 4
NUMERIC_COLUMNS_SCALE_4 = {
    "orders": ["amount"],
    "order_items": ["unit_price"],
    "payments": ["amount"],
    "refunds": ["amount"],
    "order_adjustments": ["amount"],
}

# TOASTed columns that need carry-forward
TOASTED_COLUMNS = {
    "orders": ["notes"],
    "products": ["description"],
    "customers": ["profile_json"],
    "order_items": ["custom_data"],
}

# Primary keys for each table
PRIMARY_KEYS = {
    "customers": "id",
    "products": "id",
    "orders": "id",
    "order_items": "id",
    "payments": "id",
    "refunds": "id",
    "order_adjustments": "id",
    "inventory": "id",
    "shipping": "id",
    "audit_log": "id",
}


def parse_target_schema(sql_file: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse target_schema.sql to extract table schemas with column info."""
    with open(sql_file, "r") as f:
        content = f.read()

    schemas = {}
    current_table = None
    columns = []

    for line in content.split("\n"):
        line = line.strip()

        # Skip comments and empty lines
        if not line or line.startswith("--"):
            continue

        # Detect CREATE TABLE
        create_match = re.match(r"CREATE TABLE (\w+) \(", line, re.IGNORECASE)
        if create_match:
            if current_table:
                schemas[current_table] = columns
            current_table = create_match.group(1).lower()
            columns = []
            continue

        # Detect column definitions
        if current_table and line.endswith(",") or line == ")":
            # Clean up line
            clean_line = line.rstrip(",").strip()
            if clean_line == ")":
                if current_table:
                    schemas[current_table] = columns
                    current_table = None
                    columns = []
                continue

            # Parse column: name type constraints
            # Handle complex types like NUMERIC(18,4), TIMESTAMPTZ, VARCHAR(50), etc.
            col_match = re.match(r"(\w+)\s+([\w\(\)]+)(?:\s+(.*))?", clean_line, re.IGNORECASE)
            if col_match:
                col_name = col_match.group(1).lower()
                col_type = col_match.group(2).upper()
                constraints = col_match.group(3) or ""

                # Check for NOT NULL
                nullable = "NOT NULL" not in constraints.upper()

                # Check for PRIMARY KEY
                is_pk = "PRIMARY KEY" in constraints.upper()

                # Check for DEFAULT
                default_match = re.search(r"DEFAULT\s+(.+)$", constraints, re.IGNORECASE)
                default_val = default_match.group(1) if default_match else None

                columns.append(
                    {
                        "name": col_name,
                        "type": col_type,
                        "nullable": nullable,
                        "is_primary_key": is_pk,
                        "default": default_val,
                    }
                )

    return schemas


def load_avro_schemas(schemas_dir: str) -> Dict[str, Dict]:
    """Load Avro schemas from .avsc files."""
    schemas = {}
    for filename in os.listdir(schemas_dir):
        if filename.endswith(".avsc"):
            table_name = filename[:-5]  # Remove .avsc
            with open(os.path.join(schemas_dir, filename), "r") as f:
                schema = json.load(f)
                schemas[table_name] = schema
    return schemas


def read_cdc_events(events_dir: str) -> List[Dict]:
    """Read all CDC events from partition files."""
    events = []
    for filename in sorted(os.listdir(events_dir)):
        if filename.startswith("partition_") and filename.endswith(".jsonl"):
            filepath = os.path.join(events_dir, filename)
            with open(filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
    return events


def decode_avro_payload(payload: Dict, schema: Dict) -> Dict:
    """Decode Avro-encoded payload using the schema."""
    if not payload:
        return {}
    # The payload is already decoded JSON from Debezium, but numeric values
    # are encoded as strings/bytes with scale information in the schema.
    # We need to handle the logical type decoding.
    return payload


def get_numeric_value(value: Any, source_scale: int, target_scale: int) -> Optional[Decimal]:
    """Convert numeric value from source scale to target scale by right-padding zeros."""
    if value is None:
        return None

    # Value might be a string, int, float, or Decimal
    if isinstance(value, str):
        try:
            d = Decimal(value)
        except:
            return None
    elif isinstance(value, (int, float)):
        d = Decimal(str(value))
    elif isinstance(value, Decimal):
        d = value
    else:
        return None

    # Quantize to target scale (right-pad with zeros)
    quantize_exp = Decimal("1") / (Decimal("10") ** target_scale)
    return d.quantize(quantize_exp)


def ms_to_microsecond_ts(ms: int) -> datetime:
    """Convert milliseconds since epoch to microsecond-precision datetime."""
    seconds = ms // 1000
    microseconds = (ms % 1000) * 1000
    return datetime.utcfromtimestamp(seconds).replace(microsecond=microseconds)


def parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse timestamp string to datetime with microsecond precision."""
    if not ts_str:
        return None
    # Try various formats
    for fmt in [
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
    ]:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    return None


class CDCReplayer:
    def __init__(self):
        self.target_schemas = parse_target_schema(TARGET_SCHEMA_FILE)
        self.avro_schemas = load_avro_schemas(SCHEMAS_DIR)

        # Per-key state for TOASTed column carry-forward
        # state[table][pk] = {col: value}
        self.state: Dict[str, Dict[Any, Dict[str, Any]]] = defaultdict(dict)

        # Track latest event per primary key for deduplication
        # latest[table][pk] = (lsn, event)
        self.latest_events: Dict[str, Dict[Any, Tuple[int, Dict]]] = defaultdict(dict)

    def get_column_order(self, table: str) -> List[str]:
        """Get column order from target schema."""
        if table not in self.target_schemas:
            return []
        return [col["name"] for col in self.target_schemas[table]]

    def get_column_type(self, table: str, col: str) -> str:
        """Get column type from target schema."""
        for c in self.target_schemas.get(table, []):
            if c["name"] == col:
                return c["type"]
        return "UNKNOWN"

    def is_nullable(self, table: str, col: str) -> bool:
        """Check if column is nullable in target schema."""
        for c in self.target_schemas.get(table, []):
            if c["name"] == col:
                return c["nullable"]
        return True

    def process_event(self, event: Dict) -> None:
        """Process a single CDC event and update state."""
        payload = event.get("payload", {})
        if not payload:
            return

        op = payload.get("op")
        source = payload.get("source", {})
        table = source.get("table", "").lower()
        lsn = source.get("lsn", 0)

        if not table or table not in TARGET_TABLES:
            return

        # Skip if not a table we care about
        if table == "order_adjustments":
            # This table didn't exist during CDC window, no events expected
            return

        pk_col = PRIMARY_KEYS.get(table)
        if not pk_col:
            return

        before = payload.get("before") or {}
        after = payload.get("after") or {}

        # Get primary key value
        pk_value = after.get(pk_col) or before.get(pk_col)
        if pk_value is None:
            return

        # Deduplication: keep latest by LSN
        current_latest = self.latest_events[table].get(pk_value)
        if current_latest and current_latest[0] >= lsn:
            return  # Already have a newer or equal event

        self.latest_events[table][pk_value] = (lsn, event)

        # Handle TOASTed column carry-forward
        if op in ("c", "r"):  # Create or snapshot read
            # Store all column values
            self.state[table][pk_value] = dict(after)
        elif op == "u":  # Update
            if pk_value not in self.state[table]:
                # First time seeing this key, treat as create
                self.state[table][pk_value] = dict(after)
            else:
                # Update existing state: only overwrite columns present in after
                for col, val in after.items():
                    self.state[table][pk_value][col] = val
                # Columns absent from after but in state remain unchanged (carry-forward)
        elif op == "d":  # Delete
            if pk_value in self.state[table]:
                del self.state[table][pk_value]

    def build_output_rows(self) -> Dict[str, List[Dict]]:
        """Build final output rows from processed events."""
        output = {table: [] for table in TARGET_TABLES}

        for table in TARGET_TABLES:
            if table == "order_adjustments":
                # Empty table - no events during CDC window
                continue

            pk_col = PRIMARY_KEYS[table]
            col_order = self.get_column_order(table)
            numeric_cols = NUMERIC_COLUMNS_SCALE_4.get(table, [])
            toasted_cols = TOASTED_COLUMNS.get(table, [])

            for pk_value, (lsn, event) in self.latest_events[table].items():
                payload = event.get("payload", {})
                op = payload.get("op")
                source = payload.get("source", {})
                after = payload.get("after") or {}

                # Skip deletes
                if op == "d":
                    continue

                # Get the carried-forward state for this key
                carried_state = self.state[table].get(pk_value, {})

                # Build row matching target schema column order
                row = {}
                for col in col_order:
                    if col == "processed_at" and table == "orders":
                        # Special handling for processed_at
                        row[col] = self._get_processed_at(event, carried_state, after, op)
                    elif col in numeric_cols:
                        # Numeric precision padding
                        val = carried_state.get(col, after.get(col))
                        row[col] = get_numeric_value(val, source_scale=2, target_scale=4)
                    elif col in toasted_cols:
                        # TOASTed column carry-forward
                        row[col] = carried_state.get(col)
                    else:
                        # Regular column
                        row[col] = carried_state.get(col, after.get(col))

                # Ensure all NOT NULL columns have values
                for col_info in self.target_schemas.get(table, []):
                    if not col_info["nullable"] and row.get(col_info["name"]) is None:
                        # Try to get default or use a sensible default
                        if col_info["default"]:
                            # We can't easily evaluate SQL defaults, use reasonable fallback
                            if "TIMESTAMP" in col_info["type"]:
                                row[col_info["name"]] = datetime.now()
                            elif "NUMERIC" in col_info["type"]:
                                row[col_info["name"]] = Decimal("0").quantize(Decimal("0.0001"))
                            elif "VARCHAR" in col_info["type"] or "TEXT" in col_info["type"]:
                                row[col_info["name"]] = ""
                            elif "INT" in col_info["type"] or "SERIAL" in col_info["type"]:
                                row[col_info["name"]] = 0
                            elif "BOOLEAN" in col_info["type"]:
                                row[col_info["name"]] = False

                output[table].append(row)

        return output

    def _get_processed_at(self, event: Dict, carried_state: Dict, after: Dict, op: str) -> datetime:
        """Get processed_at value following the event-time default rule."""
        source = event.get("payload", {}).get("source", {})
        ts_ms = source.get("ts_ms")

        if op == "c":
            # For inserts, use the source timestamp from CDC envelope
            if ts_ms:
                return ms_to_microsecond_ts(ts_ms)
            return datetime.now()

        elif op == "u":
            # For updates, check if processed_at was explicitly changed
            before = event.get("payload", {}).get("before") or {}
            old_val = before.get("processed_at")
            new_val = after.get("processed_at")

            # If explicitly changed (different values), use new value
            if old_val is not None and new_val is not None and old_val != new_val:
                return parse_timestamp(new_val) or datetime.now()

            # Otherwise carry forward existing value
            carried_val = carried_state.get("processed_at")
            if carried_val:
                return parse_timestamp(carried_val) or datetime.now()

            # Fallback to source timestamp
            if ts_ms:
                return ms_to_microsecond_ts(ts_ms)
            return datetime.now()

        else:  # 'r' - snapshot read
            carried_val = carried_state.get("processed_at")
            if carried_val:
                return parse_timestamp(carried_val) or datetime.now()
            if ts_ms:
                return ms_to_microsecond_ts(ts_ms)
            return datetime.now()

    def create_arrow_table(self, table: str, rows: List[Dict]) -> pa.Table:
        """Create PyArrow table with correct schema from rows."""
        if not rows:
            # Create empty table with correct schema
            return self.create_empty_arrow_table(table)

        col_order = self.get_column_order(table)
        arrays = {}

        for col in col_order:
            col_type = self.get_column_type(table, col)
            nullable = self.is_nullable(table, col)

            values = [row.get(col) for row in rows]

            if "NUMERIC" in col_type:
                # Numeric with scale 4
                arrays[col] = pa.array(
                    [v if v is not None else None for v in values],
                    type=pa.decimal128(18, 4),
                )
            elif "TIMESTAMPTZ" in col_type or "TIMESTAMP" in col_type:
                # Timestamp with microsecond precision
                ts_values = []
                for v in values:
                    if v is None:
                        ts_values.append(None)
                    elif isinstance(v, datetime):
                        ts_values.append(v)
                    else:
                        ts_values.append(parse_timestamp(str(v)) if v else None)
                arrays[col] = pa.array(ts_values, type=pa.timestamp("us", tz="UTC"))
            elif "BIGINT" in col_type or "BIGSERIAL" in col_type:
                arrays[col] = pa.array(
                    [v if v is not None else None for v in values],
                    type=pa.int64(),
                )
            elif "INTEGER" in col_type or "SERIAL" in col_type:
                arrays[col] = pa.array(
                    [v if v is not None else None for v in values],
                    type=pa.int32(),
                )
            elif "BOOLEAN" in col_type:
                arrays[col] = pa.array(
                    [v if v is not None else None for v in values],
                    type=pa.bool_(),
                )
            elif "VARCHAR" in col_type or "TEXT" in col_type or "JSONB" in col_type:
                arrays[col] = pa.array(
                    [str(v) if v is not None else None for v in values],
                    type=pa.string(),
                )
            else:
                # Default to string
                arrays[col] = pa.array(
                    [str(v) if v is not None else None for v in values],
                    type=pa.string(),
                )

        return pa.table(arrays, schema=pa.schema([(col, arrays[col].type) for col in col_order]))

    def create_empty_arrow_table(self, table: str) -> pa.Table:
        """Create empty table with correct schema."""
        col_order = self.get_column_order(table)
        fields = []

        for col in col_order:
            col_type = self.get_column_type(table, col)
            nullable = self.is_nullable(table, col)

            if "NUMERIC" in col_type:
                fields.append(pa.field(col, pa.decimal128(18, 4), nullable=nullable))
            elif "TIMESTAMPTZ" in col_type or "TIMESTAMP" in col_type:
                fields.append(pa.field(col, pa.timestamp("us", tz="UTC"), nullable=nullable))
            elif "BIGINT" in col_type or "BIGSERIAL" in col_type:
                fields.append(pa.field(col, pa.int64(), nullable=nullable))
            elif "INTEGER" in col_type or "SERIAL" in col_type:
                fields.append(pa.field(col, pa.int32(), nullable=nullable))
            elif "BOOLEAN" in col_type:
                fields.append(pa.field(col, pa.bool_(), nullable=nullable))
            elif "VARCHAR" in col_type or "TEXT" in col_type or "JSONB" in col_type:
                fields.append(pa.field(col, pa.string(), nullable=nullable))
            else:
                fields.append(pa.field(col, pa.string(), nullable=nullable))

        schema = pa.schema(fields)
        return pa.table([[] for _ in col_order], schema=schema)

    def write_parquet_files(self, output_rows: Dict[str, List[Dict]]) -> None:
        """Write output rows to Parquet files."""
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        for table in TARGET_TABLES:
            rows = output_rows.get(table, [])
            table_obj = self.create_arrow_table(table, rows)
            output_path = os.path.join(OUTPUT_DIR, f"{table}.parquet")
            pq.write_table(table_obj, output_path, compression="snappy")
            print(f"Wrote {len(rows)} rows to {output_path}")


def main():
    print("Starting CDC Replay with Schema Evolution...")

    # Initialize replayer
    replayer = CDCReplayer()

    # Read and process all events
    print("Reading CDC events...")
    events = read_cdc_events(EVENTS_DIR)
    print(f"Read {len(events)} events")

    print("Processing events...")
    for i, event in enumerate(events):
        replayer.process_event(event)
        if i % 10000 == 0 and i > 0:
            print(f"  Processed {i} events...")

    print(f"Processed all events. Latest events per table:")
    for table in TARGET_TABLES:
        if table != "order_adjustments":
            count = len(replayer.latest_events.get(table, {}))
            print(f"  {table}: {count} unique keys")

    # Build output rows
    print("Building output rows...")
    output_rows = replayer.build_output_rows()

    for table in TARGET_TABLES:
        count = len(output_rows.get(table, []))
        print(f"  {table}: {count} rows")

    # Write Parquet files
    print("Writing Parquet files...")
    replayer.write_parquet_files(output_rows)

    print("Done!")


if __name__ == "__main__":
    main()