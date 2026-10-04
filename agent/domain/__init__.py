"""
Deterministic domain layer: pure functions over a Snapshot, no network
I/O, no clock reads (an `as_of` date is always passed in explicitly).
Mirrors Team 04's prod_agent/domain split (plan.md architecture).
"""
