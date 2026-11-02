"""``BootstrapGate``: once-per-root discovery that never waits while importing, and merges its runs.
Real discovery makes interleavings a matter of luck, so these drive the gate with stub runs and
events instead: each test pins one row of the protocol (owner, waiter, import-time participant,
re-entry, failure, reset) in an order the test chooses rather than the scheduler.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import partial
from threading import Barrier, Event, Thread

import pytest
from idunn import ReportMap
from idunn.internal import BootstrapGate

from _support import ImportingCall

ROOT = 'gate_root'


class Runs:
  """Canned reports for stub discovery runs."""

  @staticmethod
  def report(
    *,
    imported: tuple[str, ...] = (ROOT,),
    skipped: tuple[str, ...] = (),
    ports: tuple[str, ...] = (),
    adapters: tuple[str, ...] = (),
  ) -> ReportMap:
    """Build the report one stub run hands back."""
    return {
      'root_package': ROOT,
      'imported_modules': imported,
      'skipped_modules': skipped,
      'registered_ports': ports,
      'registered_adapters': adapters,
    }


class Stub:
  """A ``discover`` callable that counts its calls, runs ``before``, then returns or raises."""

  def __init__(
    self,
    outcome: ReportMap | BaseException,
    *,
    before: Callable[[], object] | None = None,
  ) -> None:
    """Remember the outcome; ``before`` lets a test park the run where it wants it."""
    self.calls: int = 0
    self._outcome: ReportMap | BaseException = outcome
    self._before: Callable[[], object] | None = before

  def __call__(self) -> ReportMap:
    """Run once more."""
    self.calls += 1
    if self._before is not None:
      self._before()
    if isinstance(self._outcome, BaseException):
      raise self._outcome
    return self._outcome

  @classmethod
  def never(cls) -> Stub:
    """Return a run that fails the test if the gate ever starts it."""
    return cls(AssertionError('the gate ran a discovery it should have waited for'))


class Crew:
  """Runs callables on daemon threads and keeps what each returned or raised, by name."""

  def __init__(self) -> None:
    """Start with nobody on deck."""
    self.results: dict[str, object] = {}
    self.errors: dict[str, BaseException] = {}
    self._threads: list[Thread] = []

  def join(self) -> None:
    """Wait for everyone; a thread still running after 10 s is a deadlock and goes in ``errors``."""
    for thread in self._threads:
      thread.join(timeout=10)
    self.errors.update(
      {thread.name: TimeoutError(thread.name) for thread in self._threads if thread.is_alive()}
    )

  def start(self, name: str, target: Callable[[], object]) -> None:
    """Start ``target`` on a daemon thread called ``name``."""
    thread = Thread(target=self._guarded, args=(name, target), name=name, daemon=True)
    self._threads.append(thread)
    thread.start()

  def _guarded(self, name: str, target: Callable[[], object]) -> None:
    try:
      self.results[name] = target()
    except BaseException as error:  # the tests assert on exactly what landed here
      self.errors[name] = error


def test_first_run_is_cached_and_never_repeated() -> None:
  gate = BootstrapGate()
  report = Runs.report(adapters=('gate_root.Apple',))
  first_run = Stub(report)
  never = Stub.never()

  first = gate.run(ROOT, discover=first_run)

  assert first == report
  assert gate.run(ROOT, discover=never) is first
  assert (first_run.calls, never.calls) == (1, 0)


def test_reentrant_run_returns_its_own_report_and_the_cache_merges_both() -> None:
  gate = BootstrapGate()
  nested_report = Runs.report(
    imported=(ROOT, 'gate_root.c'),
    skipped=('gate_root.b', 'gate_root.d'),
    ports=('gate_root.c.Port',),
    adapters=('gate_root.c.First',),
  )
  outer_report = Runs.report(imported=(ROOT, 'gate_root.b'), adapters=('gate_root.b.Second',))
  nested_results: list[ReportMap] = []
  nested = Stub(nested_report)
  outer = Stub(outer_report, before=lambda: nested_results.append(gate.run(ROOT, discover=nested)))

  merged = gate.run(ROOT, discover=outer)

  assert nested_results[0] is nested_report
  # Sorted union of imports; a module skipped by one run but imported by another was only early;
  # registrations concatenate in the order the runs finished, the nested one first.
  assert merged == {
    'root_package': ROOT,
    'imported_modules': (ROOT, 'gate_root.b', 'gate_root.c'),
    'skipped_modules': ('gate_root.d',),
    'registered_ports': ('gate_root.c.Port',),
    'registered_adapters': ('gate_root.c.First', 'gate_root.b.Second'),
  }
  assert gate.run(ROOT, discover=Stub.never()) is merged


def test_a_failed_participant_is_left_out_and_the_flight_goes_on() -> None:
  gate = BootstrapGate()
  outer_report = Runs.report(adapters=('gate_root.Apple',))
  failures: list[str] = []

  def stumble() -> None:
    try:
      gate.run(ROOT, discover=Stub(RuntimeError('participant')))
    except RuntimeError as error:
      failures.append(str(error))

  merged = gate.run(ROOT, discover=Stub(outer_report, before=stumble))

  assert failures == ['participant']
  assert merged == outer_report
  assert gate.run(ROOT, discover=Stub.never()) is merged


def test_a_failed_owner_caches_nothing_and_its_participants_carry_into_the_retry() -> None:
  gate = BootstrapGate()
  participant_report = Runs.report(adapters=('gate_root.Early',))
  nested_results: list[ReportMap] = []
  owner = Stub(
    RuntimeError('owner'),
    before=lambda: nested_results.append(gate.run(ROOT, discover=Stub(participant_report))),
  )

  with pytest.raises(RuntimeError, match='owner'):
    gate.run(ROOT, discover=owner)

  # Half a bootstrap is not cached, but Early is registered for good and the retry cannot see it
  # as new, so the retry's report has to inherit it or nobody will ever list it.
  assert nested_results == [participant_report]
  retry = Stub(Runs.report(adapters=('gate_root.Retry',)))
  assert gate.run(ROOT, discover=retry)['registered_adapters'] == (
    'gate_root.Early',
    'gate_root.Retry',
  )
  assert retry.calls == 1


def test_clear_forgets_the_reports_a_failed_flight_carried() -> None:
  gate = BootstrapGate()
  owner = Stub(
    RuntimeError('owner'),
    before=partial(gate.run, ROOT, discover=Stub(Runs.report(adapters=('gate_root.Early',)))),
  )
  with pytest.raises(RuntimeError, match='owner'):
    gate.run(ROOT, discover=owner)

  gate.clear()

  retry = Stub(Runs.report(adapters=('gate_root.Retry',)))
  assert gate.run(ROOT, discover=retry)['registered_adapters'] == ('gate_root.Retry',)


def test_nested_reentries_keep_the_flight_open_until_the_outermost_run_leaves() -> None:
  gate = BootstrapGate()
  innermost = Stub(Runs.report(adapters=('gate_root.Inner',)))
  middle = Stub(
    Runs.report(adapters=('gate_root.Middle',)),
    before=partial(gate.run, ROOT, discover=innermost),
  )
  outer = Stub(
    Runs.report(adapters=('gate_root.Outer',)), before=partial(gate.run, ROOT, discover=middle)
  )

  merged = gate.run(ROOT, discover=outer)

  # Three runs on one thread are three seats: the innermost leaving must not land the flight.
  assert merged['registered_adapters'] == ('gate_root.Inner', 'gate_root.Middle', 'gate_root.Outer')
  assert gate.run(ROOT, discover=Stub.never()) is merged


def test_the_owners_thread_calling_again_while_a_straggler_flies_waits_for_the_cache() -> None:
  gate = BootstrapGate()
  owner_started, participant_joined, second_call_done = Event(), Event(), Event()
  second_call = Stub(Runs.report())
  seen: dict[str, ReportMap] = {}

  def park_owner() -> None:
    owner_started.set()
    participant_joined.wait(5)

  def park_participant() -> None:
    participant_joined.set()
    # Outlive the owner and its second call. A fixed gate makes that call wait for us, so this
    # times out; a broken one lets it rediscover and set the event at once.
    second_call_done.wait(1)

  def own() -> ReportMap:
    first = gate.run(
      ROOT, discover=Stub(Runs.report(adapters=('gate_root.a.Owned',)), before=park_owner)
    )
    # The same thread, now from an entry point: its run is over, so this is no re-entry.
    seen['second'] = gate.run(ROOT, discover=second_call)
    second_call_done.set()
    return first

  importing = ImportingCall(
    'gate_import_stale_owner',
    partial(
      gate.run,
      ROOT,
      discover=Stub(Runs.report(adapters=('gate_root.outside.Late',)), before=park_participant),
    ),
  )

  def import_mid_flight() -> object:
    owner_started.wait(5)
    return importing.run()

  crew = Crew()
  with importing.installed():
    crew.start('owner', own)
    crew.start('importer', import_mid_flight)
    crew.join()

  assert crew.errors == {}
  cached = gate.run(ROOT, discover=Stub.never())
  assert second_call.calls == 0
  assert seen['second'] is cached
  assert cached['registered_adapters'] == ('gate_root.a.Owned', 'gate_root.outside.Late')


def test_concurrent_entry_point_callers_wait_for_one_run_and_share_its_report() -> None:
  gate = BootstrapGate()
  report = Runs.report(adapters=('gate_root.Apple',))
  only_run = Stub(report, before=partial(time.sleep, 0.05))  # keep the flight open for the rest
  barrier = Barrier(8)
  crew = Crew()

  def call() -> ReportMap:
    barrier.wait()
    return gate.run(ROOT, discover=only_run)

  for index in range(8):
    crew.start(f'caller-{index}', call)
  crew.join()

  assert crew.errors == {}
  assert only_run.calls == 1
  assert all(result is crew.results['caller-0'] for result in crew.results.values())
  assert crew.results['caller-0'] == report


def test_owner_failure_wakes_the_waiters_who_each_retry_and_nothing_is_cached() -> None:
  gate = BootstrapGate()
  started, release, owner_failed = Event(), Event(), Event()
  retried_after_failure: list[bool] = []

  def park_owner() -> None:
    started.set()
    release.wait(5)
    owner_failed.set()

  crew = Crew()
  crew.start(
    'owner', partial(gate.run, ROOT, discover=Stub(RuntimeError('owner'), before=park_owner))
  )
  assert started.wait(5)
  waiters: dict[str, Stub] = {
    f'waiter-{index}': Stub(
      RuntimeError(f'waiter-{index}'),
      before=lambda: retried_after_failure.append(owner_failed.is_set()),
    )
    for index in range(3)
  }
  for name, stub in waiters.items():
    crew.start(name, partial(gate.run, ROOT, discover=stub))
  time.sleep(0.1)  # let the waiters reach the flight; the assertions hold either way
  release.set()
  crew.join()

  assert {name: str(error) for name, error in crew.errors.items()} == {
    'owner': 'owner',
    'waiter-0': 'waiter-0',
    'waiter-1': 'waiter-1',
    'waiter-2': 'waiter-2',
  }
  # Each waiter ran its own discovery exactly once, and only after the owner had failed.
  assert [stub.calls for stub in waiters.values()] == [1, 1, 1]
  assert retried_after_failure == [True, True, True]
  fresh = Stub(Runs.report(adapters=('gate_root.Apple',)))
  assert gate.run(ROOT, discover=fresh)['registered_adapters'] == ('gate_root.Apple',)
  assert fresh.calls == 1


def test_an_import_time_caller_discovers_itself_and_the_owner_caches_the_merge() -> None:
  gate = BootstrapGate()
  owner_started, participant_left = Event(), Event()
  never = Stub.never()

  def park_owner() -> None:
    owner_started.set()
    participant_left.wait(5)  # a participant that waited for the owner would time this out

  owner = Stub(Runs.report(adapters=('gate_root.a.Owned',)), before=park_owner)
  participant_report = Runs.report(adapters=('gate_root.b.Imported',))
  importing = ImportingCall(
    'gate_import_participant', partial(gate.run, ROOT, discover=Stub(participant_report))
  )

  def import_mid_flight() -> object:
    owner_started.wait(5)
    try:
      return importing.run()
    finally:
      participant_left.set()

  crew = Crew()
  with importing.installed():
    crew.start('owner', partial(gate.run, ROOT, discover=owner))
    crew.start('importer', import_mid_flight)
    assert owner_started.wait(5)
    for index in range(3):
      crew.start(f'waiter-{index}', partial(gate.run, ROOT, discover=never))
    crew.join()

  assert crew.errors == {}
  cached = gate.run(ROOT, discover=never)
  assert crew.results['importer'] is participant_report
  assert crew.results['owner'] is cached
  assert all(crew.results[f'waiter-{index}'] is cached for index in range(3))
  assert cached['registered_adapters'] == ('gate_root.b.Imported', 'gate_root.a.Owned')
  assert never.calls == 0


def test_an_import_time_caller_that_outlives_the_owner_caches_the_full_merge() -> None:
  gate = BootstrapGate()
  owner_started, participant_joined, owner_left = Event(), Event(), Event()
  owner_report = Runs.report(adapters=('gate_root.a.Owned',))
  participant_report = Runs.report(adapters=('gate_root.outside.Late',))

  def park_owner() -> None:
    owner_started.set()
    participant_joined.wait(5)

  def park_participant() -> None:
    participant_joined.set()
    owner_left.wait(5)

  def own() -> ReportMap:
    try:
      return gate.run(ROOT, discover=Stub(owner_report, before=park_owner))
    finally:
      owner_left.set()

  importing = ImportingCall(
    'gate_import_straggler',
    partial(gate.run, ROOT, discover=Stub(participant_report, before=park_participant)),
  )

  def import_mid_flight() -> object:
    owner_started.wait(5)
    return importing.run()

  crew = Crew()
  with importing.installed():
    crew.start('owner', own)
    crew.start('importer', import_mid_flight)
    crew.join()

  assert crew.errors == {}
  cached = gate.run(ROOT, discover=Stub.never())
  # The owner could not wait for the straggler, so it got the merge so far, uncached.
  assert crew.results['owner'] == owner_report
  assert crew.results['owner'] is not cached
  assert crew.results['importer'] is participant_report
  assert cached['registered_adapters'] == ('gate_root.a.Owned', 'gate_root.outside.Late')


def test_clear_mid_flight_leaves_the_run_in_the_generation_it_started_in() -> None:
  gate = BootstrapGate()
  stale = Stub(Runs.report(adapters=('gate_root.Stale',)), before=gate.clear)
  fresh = Stub(Runs.report(adapters=('gate_root.Fresh',)))

  stale_report = gate.run(ROOT, discover=stale)
  fresh_report = gate.run(ROOT, discover=fresh)

  assert stale_report['registered_adapters'] == ('gate_root.Stale',)
  assert fresh_report['registered_adapters'] == ('gate_root.Fresh',)
  assert (stale.calls, fresh.calls) == (1, 1)
