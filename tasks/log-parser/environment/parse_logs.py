#!/usr/bin/env python3
"""
Advanced Log Parser - Handles multiple log formats, rotated logs, multi-line entries,
JSON field parsing, timestamp normalization, deduplication, and streaming.
"""

import json
import re
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Iterator, Tuple
from datetime import datetime
from collections import defaultdict, Counter
import dateutil.parser


class LogParser:
    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
        self.entries = []
        self.seen_keys = set()
        self.source_counts = defaultdict(int)
        self.level_counts = defaultdict(int)
        self.request_ids = set()
        self.job_ids = set()
        self.user_ids = set()
        self.error_codes = Counter()
        self.slow_queries = []
        self.latencies = []

    def parse_value(self, value: str) -> Any:
        """Convert string value to appropriate type: int, float, bool, dict, list, or string."""
        value = value.strip()
        
        # Try JSON object/array first
        if (value.startswith('{') and value.endswith('}')) or (value.startswith('[') and value.endswith(']')):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass  # Fall through to string
        
        # Try boolean
        if value.lower() == 'true':
            return True
        if value.lower() == 'false':
            return False
        
        # Try integer
        try:
            return int(value)
        except ValueError:
            pass
        
        # Try float
        try:
            return float(value)
        except ValueError:
            pass
        
        # Return as string
        return value

    def normalize_timestamp(self, ts_str: str) -> str:
        """Normalize various timestamp formats to UTC ISO 8601 with milliseconds."""
        ts_str = ts_str.strip()
        
        # Handle space separator instead of T
        ts_str = ts_str.replace(' ', 'T', 1)
        
        # Handle slash date format (YYYY/MM/DD or DD/MM/YYYY)
        if '/' in ts_str[:10]:
            parts = ts_str.split('T')[0].split('/')
            if len(parts) == 3:
                if len(parts[0]) == 4:  # YYYY/MM/DD
                    ts_str = '-'.join(parts) + ts_str[10:]
                else:  # DD/MM/YYYY
                    ts_str = f"{parts[2]}-{parts[1]}-{parts[0]}" + ts_str[10:]
        
        # Parse with dateutil which handles many formats
        try:
            dt = dateutil.parser.parse(ts_str)
            # Convert to UTC
            if dt.tzinfo is not None:
                dt = dt.utctimetuple()
                dt = datetime(*dt[:6])
            # Format with milliseconds
            return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        except Exception:
            # Fallback: try to fix common formats manually
            return self._fallback_normalize(ts_str)

    def _fallback_normalize(self, ts_str: str) -> str:
        """Fallback timestamp normalization."""
        # Ensure we have milliseconds
        if '.' not in ts_str and 'T' in ts_str:
            # Add .000 before Z or timezone
            if ts_str.endswith('Z'):
                ts_str = ts_str[:-1] + '.000Z'
            elif '+' in ts_str or ts_str.count('-') > 2:
                # Has timezone offset
                tz_match = re.search(r'([+-]\d{2}:?\d{2})$', ts_str)
                if tz_match:
                    base = ts_str[:-len(tz_match.group(1))]
                    ts_str = base + '.000' + tz_match.group(1)
                else:
                    ts_str += '.000Z'
            else:
                ts_str += '.000Z'
        elif '.' in ts_str and 'T' in ts_str:
            # Ensure exactly 3 digits for milliseconds
            match = re.match(r'(.*\.\d{1,6})(.*)', ts_str)
            if match:
                ms_part = match.group(1)
                rest = match.group(2)
                ms_digits = ms_part.split('.')[-1]
                if len(ms_digits) < 3:
                    ms_digits = ms_digits.ljust(3, '0')
                elif len(ms_digits) > 3:
                    ms_digits = ms_digits[:3]
                ts_str = ms_part[:ms_part.rfind('.')+1] + ms_digits + rest
        
        # Ensure Z suffix for UTC
        if not ts_str.endswith('Z') and not re.search(r'[+-]\d{2}:?\d{2}$', ts_str):
            ts_str += 'Z'
        
        return ts_str

    def parse_fields(self, fields_str: str) -> Dict[str, Any]:
        """Parse KEY=VALUE pairs, handling JSON values."""
        fields = {}
        if not fields_str:
            return fields
        
        # Split by comma but respect JSON structures
        pairs = []
        current = ""
        depth = 0
        in_string = False
        escape = False
        
        for char in fields_str:
            if char == '"' and not escape:
                in_string = not in_string
            elif char == '\\' and in_string and not escape:
                escape = True
                current += char
                continue
            
            if not in_string:
                if char in '{[':
                    depth += 1
                elif char in '}]':
                    depth -= 1
                elif char == ',' and depth == 0:
                    pairs.append(current.strip())
                    current = ""
                    continue
            
            current += char
            escape = False
        
        if current:
            pairs.append(current.strip())
        
        for pair in pairs:
            if '=' in pair:
                key, value = pair.split('=', 1)
                fields[key.strip()] = self.parse_value(value)
        
        return fields

    def parse_log_line(self, line: str, source_file: str) -> Optional[Dict[str, Any]]:
        """Parse a single log line, return entry or None if continuation."""
        line = line.rstrip('\n')
        if not line.strip():
            return None
        
        # Check if this is a continuation line (starts with whitespace or tab)
        if line.startswith(' ') or line.startswith('\t'):
            return {'_continuation': line.strip()}
        
        # Main log pattern with flexible timestamp
        pattern = r'^\[(INFO|ERROR|WARN|DEBUG|CRITICAL)\]\s+(.+?)\s+-\s+(.+?)(?:\s+-\s+(.+))?$'
        match = re.match(pattern, line)
        
        if not match:
            print(f"WARNING: Skipping malformed line in {source_file}: {line[:100]}", file=sys.stderr)
            return None
        
        level, timestamp, message, fields_str = match.groups()
        
        # Normalize timestamp
        normalized_ts = self.normalize_timestamp(timestamp)
        
        # Parse fields
        fields = self.parse_fields(fields_str) if fields_str else {}
        
        # Create deduplication key
        dedup_key = None
        if 'request_id' in fields:
            dedup_key = (normalized_ts, level, message, fields['request_id'])
        elif 'job_id' in fields:
            dedup_key = (normalized_ts, level, message, fields['job_id'])
        else:
            dedup_key = (normalized_ts, level, message)
        
        return {
            'level': level,
            'timestamp': normalized_ts,
            'message': message.strip(),
            'fields': fields,
            '_source': source_file,
            '_dedup_key': dedup_key
        }

    def process_file(self, filepath: Path) -> Iterator[Dict[str, Any]]:
        """Process a single log file, yielding complete entries."""
        current_entry = None
        
        with open(filepath, 'r') as f:
            for line in f:
                parsed = self.parse_log_line(line, filepath.name)
                
                if parsed is None:
                    continue
                
                if '_continuation' in parsed:
                    # Continuation line - append to current entry's message or stack_trace
                    if current_entry:
                        cont = parsed['_continuation']
                        # If it looks like a stack trace, append to stack_trace field
                        if 'stack_trace' in current_entry['fields']:
                            current_entry['fields']['stack_trace'] += '\n' + cont
                        else:
                            current_entry['message'] += ' ' + cont
                    continue
                
                # New entry - yield previous if exists
                if current_entry:
                    yield current_entry
                
                current_entry = parsed
            
            # Yield last entry
            if current_entry:
                yield current_entry

    def get_log_files_sorted(self) -> List[Path]:
        """Get all log files sorted by rotation order (base.1, base, base.2, etc.)."""
        log_files = list(self.logs_dir.glob('*.log*'))
        # Group by base name
        groups = defaultdict(list)
        for f in log_files:
            name = f.name
            if re.match(r'.*\.log\.\d+$', name):
                base = re.sub(r'\.log\.\d+$', '.log', name)
            else:
                base = name
            groups[base].append(f)
        
        sorted_files = []
        for base, files in groups.items():
            # Sort: .log.1, .log, .log.2, .log.3...
            def sort_key(f):
                name = f.name
                if name == base:
                    return (0, 0)
                match = re.match(r'.*\.log\.(\d+)$', name)
                if match:
                    return (1, int(match.group(1)))
                return (2, name)
            files.sort(key=sort_key)
            sorted_files.extend(files)
        
        return sorted_files

    def collect_stats(self, entry: Dict[str, Any]):
        """Collect statistics from an entry."""
        self.level_counts[entry['level']] += 1
        self.source_counts[entry['_source']] += 1
        
        fields = entry['fields']
        if 'request_id' in fields:
            self.request_ids.add(fields['request_id'])
        if 'job_id' in fields:
            self.job_ids.add(fields['job_id'])
        if 'user_id' in fields:
            self.user_ids.add(fields['user_id'])
        if 'error_code' in fields:
            self.error_codes[fields['error_code']] += 1
        if 'latency_ms' in fields and isinstance(fields['latency_ms'], (int, float)):
            self.latencies.append(fields['latency_ms'])
        if 'query_id' in fields and 'duration_s' in fields:
            self.slow_queries.append({
                'query_id': fields['query_id'],
                'duration_s': fields['duration_s']
            })

    def run(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Run the parser on all log files."""
        log_files = self.get_log_files_sorted()
        
        for log_file in log_files:
            for entry in self.process_file(log_file):
                # Check deduplication
                if entry['_dedup_key'] in self.seen_keys:
                    continue
                self.seen_keys.add(entry['_dedup_key'])
                
                # Collect stats
                self.collect_stats(entry)
                
                # Clean up internal fields
                clean_entry = {
                    'level': entry['level'],
                    'timestamp': entry['timestamp'],
                    'message': entry['message'],
                    'fields': entry['fields']
                }
                self.entries.append(clean_entry)
        
        # Sort by timestamp
        self.entries.sort(key=lambda e: e['timestamp'])
        
        # Generate aggregated stats
        total = len(self.entries)
        stats = {
            'total_entries': total,
            'by_level': dict(self.level_counts),
            'by_source': dict(self.source_counts),
            'time_range': {
                'start': self.entries[0]['timestamp'] if self.entries else '',
                'end': self.entries[-1]['timestamp'] if self.entries else ''
            },
            'unique_request_ids': len(self.request_ids),
            'unique_job_ids': len(self.job_ids),
            'unique_user_ids': len(self.user_ids),
            'error_rate': round(self.level_counts.get('ERROR', 0) / total, 2) if total > 0 else 0,
            'avg_latency_ms': round(sum(self.latencies) / len(self.latencies), 1) if self.latencies else 0,
            'top_errors': [
                {'error_code': code, 'count': count}
                for code, count in self.error_codes.most_common(10)
            ],
            'slow_queries': self.slow_queries
        }
        
        return self.entries, stats


def main():
    logs_dir = Path('/app/logs')
    output_parsed = Path('/app/parsed_logs.json')
    output_stats = Path('/app/aggregated_stats.json')
    
    if not logs_dir.exists():
        print(f"ERROR: Logs directory {logs_dir} does not exist", file=sys.stderr)
        sys.exit(1)
    
    parser = LogParser(logs_dir)
    entries, stats = parser.run()
    
    # Write parsed logs
    with open(output_parsed, 'w') as f:
        json.dump(entries, f, indent=2)
    
    # Write aggregated stats
    with open(output_stats, 'w') as f:
        json.dump(stats, f, indent=2)
    
    print(f"Total entries parsed: {len(entries)}")
    print(f"Output written to {output_parsed} and {output_stats}")


if __name__ == '__main__':
    main()