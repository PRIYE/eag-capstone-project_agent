"""
Root pytest conftest. Puts the repo root on sys.path so `agent/` and
`harness/` import cleanly regardless of where pytest is invoked from, and
guarantees tests never touch the real network: no test in tests/ should
need it, but this is a belt-and-suspenders guard per Constitution
Principle VII (scoped change only / never touch shared data in tests).
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
