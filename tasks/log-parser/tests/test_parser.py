import json
import pytest
import sys
import os
import re
from collections import Counter

sys.path.insert(0, '/app')

EXPECTED_FILES = {
    'app.log': 10,
    'app.log.1': 10,
    'service.log': 9,
    'service.log.1': 10,
    'api.log': 16,  # 18 lines minus 2 malformed
    'access.log': 20,
    'timestamps.log': 10,
    'empty.log': 0,
}

# After deduplication: app.log.1 (10) + app.log (10) but some may overlap in time
# service.log.1 (10) + service.log (9)
# Total unique entries should be around 75 (exact count in test)
EXPECTED_MIN_ENTRIES = 70
EXPECTED_MAX_ENTRIES = 85


def load_parsed_logs():
    output_path = '/app/parsed_logs.json'
    assert os.path.exists(output_path), f"Output file {output_path} does not exist"
    with open(output_path, 'r') as f:
        data = json.load(f)
    assert isinstance(data, list), "Parsed logs should be a JSON array"
    return data


def load_aggregated_stats():
    output_path = '/app/aggregated_stats.json'
    assert os.path.exists(output_path), f"Output file {output_path} does not exist"
    with open(output_path, 'r') as f:
        data = json.load(f)
    assert isinstance(data, dict), "Aggregated stats should be a JSON object"
    return data


class TestParsedLogs:
    def test_output_file_exists(self):
        data = load_parsed_logs()
        assert len(data) >= EXPECTED_MIN_ENTRIES, f"Expected at least {EXPECTED_MIN_ENTRIES} entries, got {len(data)}"
        assert len(data) <= EXPECTED_MAX_ENTRIES, f"Expected at most {EXPECTED_MAX_ENTRIES} entries, got {len(data)}"

    def test_entry_structure(self):
        data = load_parsed_logs()
        for entry in data:
            assert 'level' in entry, "Entry missing 'level' field"
            assert 'timestamp' in entry, "Entry missing 'timestamp' field"
            assert 'message' in entry, "Entry missing 'message' field"
            assert 'fields' in entry, "Entry missing 'fields' field"
            assert isinstance(entry['fields'], dict), "'fields' should be a dictionary"
            assert entry['level'] in ['INFO', 'ERROR', 'WARN', 'DEBUG', 'CRITICAL'], f"Invalid level: {entry['level']}"
            # Timestamp format: ISO 8601 with milliseconds and Z
            assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$', entry['timestamp']), \
                f"Invalid timestamp format: {entry['timestamp']}"

    def test_chronological_order(self):
        data = load_parsed_logs()
        timestamps = [entry['timestamp'] for entry in data]
        assert timestamps == sorted(timestamps), "Entries must be sorted chronologically by timestamp"

    def test_type_inference_int(self):
        data = load_parsed_logs()
        for entry in data:
            for key, value in entry['fields'].items():
                if isinstance(value, str) and value.isdigit() and key not in ['session_id', 'request_id', 'trace_id', 'span_id', 'backup_id', 'job_id', 'query_id', 'client_id', 'user_agent', 'error', 'version', 'config_path', 'disk', 'mount', 'device', 'protocol', 'origin', 'type', 'action', 'channels', 'code', 'reason', 'checksum', 'format']:
                    pytest.fail(f"Field '{key}' should be int but is string: '{value}'")

    def test_type_inference_float(self):
        data = load_parsed_logs()
        float_fields = ['memory_percent', 'threshold', 'duration_ms', 'duration_s', 'amount', 'free_percent', 'threshold_percent', 'size_mb', 'heap_mb', 'throughput', 'avg_latency_ms', 'latency_ms', 'remaining', 'limit', 'window_sec', 'messages_sent', 'messages_received', 'value']
        for entry in data:
            for key, value in entry['fields'].items():
                if key in float_fields and isinstance(value, str):
                    try:
                        float(value)
                        pytest.fail(f"Field '{key}' should be float but is string: '{value}'")
                    except ValueError:
                        pass

    def test_type_inference_bool(self):
        data = load_parsed_logs()
        for entry in data:
            for key, value in entry['fields'].items():
                if key in ['auth_present'] and isinstance(value, str):
                    if value.lower() in ['true', 'false']:
                        pytest.fail(f"Field '{key}' should be bool but is string: '{value}'")

    def test_type_inference_json_object(self):
        data = load_parsed_logs()
        for entry in data:
            for key, value in entry['fields'].items():
                if key in ['metadata', 'error_details', 'process_info', 'query_plan', 'payment_info', 'config', 'headers', 'stats', 'body', 'tags', 'spans', 'stack_trace'] and isinstance(value, str):
                    # Check if it looks like JSON but wasn't parsed
                    if value.startswith('{') or value.startswith('['):
                        pytest.fail(f"Field '{key}' should be dict/list but is string: '{value[:100]}'")

    def test_json_object_parsing(self):
        data = load_parsed_logs()
        # Find entry with metadata JSON object
        login_entry = next((e for e in data if e['message'] == 'User login successful'), None)
        assert login_entry is not None, "Missing 'User login successful' entry"
        assert 'metadata' in login_entry['fields'], "Missing metadata field"
        assert isinstance(login_entry['fields']['metadata'], dict), "metadata should be dict"
        assert login_entry['fields']['metadata']['device'] == 'mobile'
        assert login_entry['fields']['metadata']['os'] == 'iOS 17.2'

    def test_json_array_parsing(self):
        data = load_parsed_logs()
        logout_entry = next((e for e in data if e['message'] == 'User logout'), None)
        assert logout_entry is not None, "Missing 'User logout' entry"
        assert 'events' in logout_entry['fields'], "Missing events field"
        assert isinstance(logout_entry['fields']['events'], list), "events should be list"
        assert len(logout_entry['fields']['events']) == 3
        assert logout_entry['fields']['events'][2]['amount'] == 49.99

    def test_stack_trace_preserved(self):
        data = load_parsed_logs()
        batch_error = next((e for e in data if e['message'] == 'Batch job failed'), None)
        assert batch_error is not None, "Missing 'Batch job failed' entry"
        assert 'stack_trace' in batch_error['fields'], "Missing stack_trace field"
        stack = batch_error['fields']['stack_trace']
        assert isinstance(stack, str), "stack_trace should be string"
        assert 'OutOfMemoryError' in stack
        assert 'BatchProcessor.java' in stack
        assert '\n' in stack or '\\n' in stack, "Stack trace should preserve newlines"

    def test_rotated_logs_processed(self):
        data = load_parsed_logs()
        # Check that we have entries from rotated files (app.log.1, service.log.1)
        # by looking for known messages from those files
        service_start_msgs = [e for e in data if 'Previous batch job completed' in e['message']]
        assert len(service_start_msgs) >= 1, "Missing entries from service.log.1"
        app_start_msgs = [e for e in data if 'Service starting' in e['message']]
        assert len(app_start_msgs) >= 1, "Missing entries from app.log.1"

    def test_deduplication(self):
        data = load_parsed_logs()
        # Check for duplicates by (timestamp, level, message, request_id/job_id)
        # Only flag as duplicate if the deduplication key matches exactly
        seen = set()
        duplicates = 0
        for entry in data:
            fields = entry['fields']
            # Build the same dedup key as the parser
            if 'request_id' in fields:
                key = (entry['timestamp'], entry['level'], entry['message'], fields['request_id'])
            elif 'job_id' in fields:
                key = (entry['timestamp'], entry['level'], entry['message'], fields['job_id'])
            else:
                key = (entry['timestamp'], entry['level'], entry['message'])
            if key in seen:
                duplicates += 1
            seen.add(key)
        assert duplicates == 0, f"Found {duplicates} duplicate entries after deduplication"

    def test_malformed_lines_skipped(self):
        data = load_parsed_logs()
        for entry in data:
            assert 'malformed' not in entry['message'].lower()
            assert 'should be skipped' not in entry['message'].lower()

    def test_timestamp_normalization(self):
        data = load_parsed_logs()
        for entry in data:
            ts = entry['timestamp']
            # Must be ISO 8601 UTC with milliseconds
            assert ts.endswith('Z'), f"Timestamp not UTC: {ts}"
            assert '.' in ts and ts.index('.') == 19, f"Missing milliseconds: {ts}"
            ms_part = ts[20:23]
            assert ms_part.isdigit(), f"Invalid milliseconds: {ts}"

    def test_various_timestamp_formats(self):
        data = load_parsed_logs()
        # Check that timestamp.log entries were parsed with normalized timestamps
        ts_entries = [e for e in data if 'Event with' in e['message']]
        assert len(ts_entries) == 10, f"Expected 10 timestamp test entries, got {len(ts_entries)}"
        for entry in ts_entries:
            ts = entry['timestamp']
            assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$', ts), f"Bad timestamp: {ts}"

    def test_all_levels_present(self):
        data = load_parsed_logs()
        levels = set(e['level'] for e in data)
        assert levels == {'INFO', 'ERROR', 'WARN', 'DEBUG', 'CRITICAL'}, f"Missing levels: {levels}"

    def test_critical_entry(self):
        data = load_parsed_logs()
        critical = [e for e in data if e['level'] == 'CRITICAL']
        assert len(critical) >= 1
        disk_critical = next((e for e in critical if 'Disk space critical' in e['message']), None)
        assert disk_critical is not None
        assert disk_critical['fields']['free_percent'] == 3.2
        assert isinstance(disk_critical['fields']['mounts'], list)
        assert disk_critical['fields']['mounts'][0]['free_gb'] == 2.1


class TestAggregatedStats:
    def test_stats_file_exists(self):
        stats = load_aggregated_stats()
        assert 'total_entries' in stats
        assert stats['total_entries'] >= EXPECTED_MIN_ENTRIES

    def test_by_level_counts(self):
        stats = load_aggregated_stats()
        data = load_parsed_logs()
        actual_by_level = Counter(e['level'] for e in data)
        assert stats['by_level'] == dict(actual_by_level), f"Level counts mismatch: {stats['by_level']} vs {dict(actual_by_level)}"

    def test_by_source_counts(self):
        stats = load_aggregated_stats()
        assert 'by_source' in stats
        assert isinstance(stats['by_source'], dict)
        # Should have all source files
        expected_sources = {'app.log', 'app.log.1', 'service.log', 'service.log.1', 'api.log', 'access.log', 'timestamps.log'}
        for src in expected_sources:
            assert src in stats['by_source'], f"Missing source {src} in by_source"

    def test_time_range(self):
        stats = load_aggregated_stats()
        data = load_parsed_logs()
        assert 'time_range' in stats
        assert stats['time_range']['start'] == data[0]['timestamp']
        assert stats['time_range']['end'] == data[-1]['timestamp']

    def test_unique_request_ids(self):
        stats = load_aggregated_stats()
        data = load_parsed_logs()
        request_ids = set()
        for entry in data:
            if 'request_id' in entry['fields']:
                request_ids.add(entry['fields']['request_id'])
        assert stats['unique_request_ids'] == len(request_ids)

    def test_unique_job_ids(self):
        stats = load_aggregated_stats()
        data = load_parsed_logs()
        job_ids = set()
        for entry in data:
            if 'job_id' in entry['fields']:
                job_ids.add(entry['fields']['job_id'])
        assert stats['unique_job_ids'] == len(job_ids)

    def test_unique_user_ids(self):
        stats = load_aggregated_stats()
        data = load_parsed_logs()
        user_ids = set()
        for entry in data:
            if 'user_id' in entry['fields']:
                user_ids.add(entry['fields']['user_id'])
        assert stats['unique_user_ids'] == len(user_ids)

    def test_error_rate(self):
        stats = load_aggregated_stats()
        data = load_parsed_logs()
        total = len(data)
        errors = sum(1 for e in data if e['level'] == 'ERROR')
        expected_rate = round(errors / total, 2)
        assert abs(stats['error_rate'] - expected_rate) < 0.01, f"Error rate mismatch: {stats['error_rate']} vs {expected_rate}"

    def test_avg_latency_ms(self):
        stats = load_aggregated_stats()
        data = load_parsed_logs()
        latencies = []
        for entry in data:
            if 'latency_ms' in entry['fields']:
                latencies.append(entry['fields']['latency_ms'])
        if latencies:
            expected_avg = round(sum(latencies) / len(latencies), 1)
            assert abs(stats['avg_latency_ms'] - expected_avg) < 1.0, f"Avg latency mismatch: {stats['avg_latency_ms']} vs {expected_avg}"

    def test_top_errors(self):
        stats = load_aggregated_stats()
        assert 'top_errors' in stats
        assert isinstance(stats['top_errors'], list)
        # Should have DB_CONN_ERROR and PAYMENT_DECLINED
        error_codes = [e['error_code'] for e in stats['top_errors']]
        assert 'DB_CONN_ERROR' in error_codes
        assert 'PAYMENT_DECLINED' in error_codes

    def test_slow_queries(self):
        stats = load_aggregated_stats()
        assert 'slow_queries' in stats
        assert isinstance(stats['slow_queries'], list)
        # Should have q_456 with duration 5.2
        slow = next((q for q in stats['slow_queries'] if q.get('query_id') == 'q_456'), None)
        assert slow is not None, "Missing slow query q_456"
        assert slow['duration_s'] == 5.2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])