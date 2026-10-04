"""(hand-written) RunBudget and ReadDedup, tasks.md T015."""
from agent.safety import RunBudget, ReadDedup


class _FakeClock:
    def __init__(self, start=0.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_must_finalize_true_when_two_steps_remaining():
    budget = RunBudget(max_steps=5, deadline_s=1000, clock=_FakeClock())
    budget.steps_used = 3  # 2 remaining
    assert budget.must_finalize() is True


def test_must_finalize_false_with_plenty_of_steps_and_time():
    budget = RunBudget(max_steps=20, deadline_s=180, clock=_FakeClock())
    budget.steps_used = 1
    assert budget.must_finalize() is False


def test_must_finalize_true_when_twenty_seconds_remaining():
    clock = _FakeClock(start=0.0)
    budget = RunBudget(max_steps=20, deadline_s=180, clock=clock)
    clock.advance(161)  # 19s remaining < finalize_seconds_remaining (20)
    assert budget.must_finalize() is True


def test_exhausted_on_step_limit():
    budget = RunBudget(max_steps=2, deadline_s=1000, clock=_FakeClock())
    budget.record_step()
    budget.record_step()
    assert budget.exhausted() is True


def test_exhausted_on_deadline():
    clock = _FakeClock()
    budget = RunBudget(max_steps=100, deadline_s=10, clock=clock)
    clock.advance(11)
    assert budget.exhausted() is True


def test_dedup_returns_cached_for_identical_read():
    dedup = ReadDedup()
    calls = []

    def do_call():
        calls.append(1)
        return {"data": [1, 2, 3]}

    result1, cached1 = dedup.call_deduped("Project.list", {"offset": 0}, do_call)
    result2, cached2 = dedup.call_deduped("Project.list", {"offset": 0}, do_call)

    assert cached1 is False
    assert cached2 is True
    assert result1 == result2
    assert len(calls) == 1  # second call short-circuited, do_call not invoked again


def test_dedup_runs_read_with_different_arguments():
    dedup = ReadDedup()
    calls = []

    def do_call_factory(n):
        def do_call():
            calls.append(n)
            return {"data": n}
        return do_call

    dedup.call_deduped("Project.list", {"offset": 0}, do_call_factory(1))
    dedup.call_deduped("Project.list", {"offset": 200}, do_call_factory(2))

    assert calls == [1, 2]
