#!/usr/bin/env python3
"""
Generate synthetic CDC events with schema evolution for the cdc-schema-evolution task.

Schema evolution timeline:
- v1 (events 1-2000): Original schema
  - id: BIGINT PRIMARY KEY
  - user_id: BIGINT NOT NULL
  - email: VARCHAR(50) NOT NULL
  - status: VARCHAR(20) NOT NULL DEFAULT 'active'
  - created_at: TIMESTAMP NOT NULL

- v2 (events 2001-3500): ALTER TABLE users ALTER COLUMN email TYPE VARCHAR(200)
  - email widened from VARCHAR(50) to VARCHAR(200)

- v3 (events 3501-4500): ALTER TABLE users ALTER COLUMN user_id DROP NOT NULL,
                          ALTER TABLE users RENAME COLUMN user_id TO customer_id
  - user_id nullable, renamed to customer_id

- v4 (events 4501-5000): ALTER TABLE users ADD COLUMN metadata JSONB DEFAULT '{}'::jsonb
  - new JSONB column with default empty object
"""

import json
import random
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Seed for reproducibility
random.seed(42)

# Schema versions
SCHEMAS = {
    1: {
        "version": 1,
        "table": "users",
        "columns": [
            {"name": "id", "type": "BIGINT", "nullable": False, "primary_key": True},
            {"name": "user_id", "type": "BIGINT", "nullable": False},
            {"name": "email", "type": "VARCHAR(50)", "nullable": False},
            {"name": "status", "type": "VARCHAR(20)", "nullable": False, "default": "active"},
            {"name": "created_at", "type": "TIMESTAMP", "nullable": False},
        ],
        "effective_from": 1,
        "effective_to": 2000,
    },
    2: {
        "version": 2,
        "table": "users",
        "columns": [
            {"name": "id", "type": "BIGINT", "nullable": False, "primary_key": True},
            {"name": "user_id", "type": "BIGINT", "nullable": False},
            {"name": "email", "type": "VARCHAR(200)", "nullable": False},
            {"name": "status", "type": "VARCHAR(20)", "nullable": False, "default": "active"},
            {"name": "created_at", "type": "TIMESTAMP", "nullable": False},
        ],
        "effective_from": 2001,
        "effective_to": 3500,
    },
    3: {
        "version": 3,
        "table": "users",
        "columns": [
            {"name": "id", "type": "BIGINT", "nullable": False, "primary_key": True},
            {"name": "customer_id", "type": "BIGINT", "nullable": True},  # renamed, nullable
            {"name": "email", "type": "VARCHAR(200)", "nullable": False},
            {"name": "status", "type": "VARCHAR(20)", "nullable": False, "default": "active"},
            {"name": "created_at", "type": "TIMESTAMP", "nullable": False},
        ],
        "effective_from": 3501,
        "effective_to": 4500,
    },
    4: {
        "version": 4,
        "table": "users",
        "columns": [
            {"name": "id", "type": "BIGINT", "nullable": False, "primary_key": True},
            {"name": "customer_id", "type": "BIGINT", "nullable": True},
            {"name": "email", "type": "VARCHAR(200)", "nullable": False},
            {"name": "status", "type": "VARCHAR(20)", "nullable": False, "default": "active"},
            {"name": "created_at", "type": "TIMESTAMP", "nullable": False},
            {"name": "metadata", "type": "JSONB", "nullable": False, "default": "{}"},
        ],
        "effective_from": 4501,
        "effective_to": 5000,
    },
}

# Schema history for the task
SCHEMA_HISTORY = {
    "table": "users",
    "migrations": [
        {
            "version": 1,
            "description": "Initial schema",
            "ddl": "CREATE TABLE users (id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, email VARCHAR(50) NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'active', created_at TIMESTAMP NOT NULL);",
            "effective_from_event": 1,
        },
        {
            "version": 2,
            "description": "Widen email column from VARCHAR(50) to VARCHAR(200)",
            "ddl": "ALTER TABLE users ALTER COLUMN email TYPE VARCHAR(200);",
            "effective_from_event": 2001,
            "column_changes": [
                {"column": "email", "old_type": "VARCHAR(50)", "new_type": "VARCHAR(200)", "action": "widen"}
            ],
        },
        {
            "version": 3,
            "description": "Drop NOT NULL on user_id, rename user_id to customer_id",
            "ddl": "ALTER TABLE users ALTER COLUMN user_id DROP NOT NULL; ALTER TABLE users RENAME COLUMN user_id TO customer_id;",
            "effective_from_event": 3501,
            "column_changes": [
                {"column": "user_id", "action": "drop_not_null"},
                {"column": "user_id", "new_name": "customer_id", "action": "rename"},
            ],
        },
        {
            "version": 4,
            "description": "Add metadata JSONB column with default '{}'",
            "ddl": "ALTER TABLE users ADD COLUMN metadata JSONB NOT NULL DEFAULT '{}'::jsonb;",
            "effective_from_event": 4501,
            "column_changes": [
                {"column": "metadata", "type": "JSONB", "default": "{}", "action": "add"},
            ],
        },
    ],
}

# Generate sample data
DOMAINS = ["example.com", "test.org", "company.net", "demo.io", "sample.dev"]
STATUSES = ["active", "inactive", "pending", "suspended", "archived"]
FIRST_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry", "Iris", "Jack"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]


def generate_email(first: str, last: str, num: int) -> str:
    """Generate email, some will be long (>50 chars) for v2+"""
    if num % 7 == 0:  # ~14% will be long emails
        return f"{first.lower()}.{last.lower()}.{num}.verylongsubdomain@enterprise-corporation-international.example.com"
    return f"{first.lower()}.{last.lower()}{num}@{random.choice(DOMAINS)}"


def generate_metadata(event_num: int) -> Dict[str, Any]:
    """Generate metadata JSONB for v4 events"""
    types = ["premium", "standard", "trial", "enterprise"]
    return {
        "tier": random.choice(types),
        "features": random.sample(["api", "dashboard", "reports", "integrations", "sso", "audit"], k=random.randint(1, 4)),
        "last_login": (datetime(2024, 1, 1) + timedelta(days=random.randint(0, 365))).isoformat(),
        "referral_code": f"REF{event_num:06d}" if event_num % 3 == 0 else None,
    }


def get_schema_for_event(event_num: int) -> Dict:
    """Get the schema version for a given event number"""
    for schema in SCHEMAS.values():
        if schema["effective_from"] <= event_num <= schema["effective_to"]:
            return schema
    return SCHEMAS[1]


def generate_event(event_num: int) -> Dict[str, Any]:
    """Generate a single CDC event"""
    schema = get_schema_for_event(event_num)
    version = schema["version"]
    
    # Determine operation type
    if event_num <= 50:
        op = "INSERT"
    elif event_num <= 100:
        op = "DELETE"
    else:
        op = random.choices(["INSERT", "UPDATE", "DELETE"], weights=[0.5, 0.35, 0.15])[0]
    
    # Generate base values
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    user_id = random.randint(10000, 99999)
    email = generate_email(first, last, event_num)
    status = random.choice(STATUSES)
    created_at = datetime(2024, 1, 1) + timedelta(seconds=event_num * 10)
    
    # Build before/after images based on schema version and operation
    if version == 1:
        # v1: user_id, email(VARCHAR50), status, created_at
        row = {
            "id": event_num,
            "user_id": user_id,
            "email": email[:50],  # Truncate to 50 for v1
            "status": status,
            "created_at": created_at.isoformat(),
        }
    elif version == 2:
        # v2: user_id, email(VARCHAR200), status, created_at
        row = {
            "id": event_num,
            "user_id": user_id,
            "email": email,  # Full email, up to 200 chars
            "status": status,
            "created_at": created_at.isoformat(),
        }
    elif version == 3:
        # v3: customer_id (nullable), email(VARCHAR200), status, created_at
        row = {
            "id": event_num,
            "customer_id": user_id if random.random() > 0.1 else None,  # 10% null
            "email": email,
            "status": status,
            "created_at": created_at.isoformat(),
        }
    else:  # version 4
        # v4: customer_id, email, status, created_at, metadata
        row = {
            "id": event_num,
            "customer_id": user_id if random.random() > 0.1 else None,
            "email": email,
            "status": status,
            "created_at": created_at.isoformat(),
            "metadata": generate_metadata(event_num),
        }
    
    event = {
        "event_id": f"evt_{event_num:05d}",
        "event_num": event_num,
        "schema_version": version,
        "table": "users",
        "operation": op,
        "timestamp": (datetime(2024, 1, 1) + timedelta(seconds=event_num * 10 + random.randint(0, 5))).isoformat(),
        "lsn": 1000000 + event_num,  # Log sequence number
    }
    
    if op == "INSERT":
        event["after"] = row
        event["before"] = None
    elif op == "DELETE":
        event["before"] = row
        event["after"] = None
    else:  # UPDATE
        # For UPDATE, create a slightly modified version
        before_row = row.copy()
        after_row = row.copy()
        
        # Modify one field
        if version >= 3 and "customer_id" in after_row:
            after_row["customer_id"] = user_id + 1000
        elif "user_id" in after_row:
            after_row["user_id"] = user_id + 1000
            
        if "email" in after_row:
            after_row["email"] = generate_email(first, last, event_num + 1000)
        if "status" in after_row:
            after_row["status"] = random.choice([s for s in STATUSES if s != status])
        if version == 4 and "metadata" in after_row:
            after_row["metadata"]["last_login"] = (datetime(2024, 1, 1) + timedelta(days=random.randint(0, 365))).isoformat()
        
        event["before"] = before_row
        event["after"] = after_row
    
    return event


def main():
    import os
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    
    # Generate schema history file
    schema_history_path = os.path.join(data_dir, "schema_history.json")
    with open(schema_history_path, "w") as f:
        json.dump(SCHEMA_HISTORY, f, indent=2)
    
    # Generate CDC events in batches (simulate multiple files)
    events = []
    for i in range(1, 5001):
        events.append(generate_event(i))
    
    # Split into 5 files
    batch_size = 1000
    for batch_idx in range(5):
        start = batch_idx * batch_size
        end = start + batch_size
        batch = events[start:end]
        
        filename = os.path.join(data_dir, f"cdc_events_{batch_idx + 1:02d}.jsonl")
        with open(filename, "w") as f:
            for event in batch:
                f.write(json.dumps(event) + "\n")
        
        print(f"Generated {filename} with {len(batch)} events")
    
    print(f"Generated {schema_history_path}")
    print("Done!")


if __name__ == "__main__":
    main()