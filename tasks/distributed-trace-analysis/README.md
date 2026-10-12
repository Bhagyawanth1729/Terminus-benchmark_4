# Distributed Trace Root-Cause Analysis with Clock Skew

## Difficulty explanation
This task requires 4 hours for an expert SRE/distributed systems engineer. The core challenge is recognizing that wall-clock timestamps are unreliable across unsynchronized hosts and that causality must be reconstructed from the span parent-child linkage (parentSpanId), not from timestamp ordering. The clock skew trap (-1.8s on database) makes the database span appear to have the longest wall-clock duration (3.2s), but it completed successfully (status OK). The true root cause is the payment-service timeout, which requires walking the causal critical path from the gateway's 504 error.

## Solution explanation
The solution parses the JSONL trace, builds a spanId-indexed graph, finds the root span (parentSpanId=null), and walks the critical path by following parentSpanId→spanId links, preferring children with ERROR/TIMEOUT status. The leaf of this path (payment-service with TIMEOUT) is the root cause. gateway_misconfig is false because the downstream service genuinely timed out, not because the gateway's timeout was too short.

## Verification explanation
The verifier loads `/app/analysis.json` and checks exact equality against the expected output: root_cause_service="payment-service", root_cause_error_code="TIMEOUT", gateway_misconfig=false, and a critical_path array of exactly 3 spans (api-gateway→order-service→payment-service). No tolerance ranges; exact match required.

## Relevant experience
This task mirrors real SRE incident response for microservices. An engineer with 3+ years running production distributed systems (e.g., at a cloud-native company) would have debugged cascading failures where clock skew misled initial investigation. The trap—blaming the database because its span looks slowest—is a classic pitfall that only experience with distributed tracing (OpenTelemetry, Jaeger, Zipkin) reveals.