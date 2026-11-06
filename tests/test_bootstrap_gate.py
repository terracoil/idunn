"""``BootstrapGate``: once-per-root discovery that never waits while importing, and merges its runs.
Real discovery makes interleavings a matter of luck, so these drive the gate with stub runs and
events instead: each test pins one row of the protocol (owner, waiter, import-time participant,
re-entry, failure, reset) in an order the test chooses rather than the scheduler.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import partial
from threading import Barrier, Event
from typing import Any

import pytest

from idunn import ReportMap
from idunn.internal import BootstrapGate

from _support import ImportingCall, Racer

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


class LateCache(dict[str, ReportMap]):
  """A report cache whose first read misses, filled by "another thread" right after that read.
  That is the interleaving the second look under the gate's lock exists for. Without it, the late
  caller boards a flight of its own, rediscovers, finds nothing new, and caches an empty report
  over the full one.
  """

  def __init__(self, cached: ReportMap) -> None:
    """Hold ``cached`` back until the first read has missed."""
    super().__init__()
    self._cached: ReportMap = cached
    self._reads: int = 0

  def get(self, key: str, default: Any = None) -> Any:
    """Miss once, caching the report as the miss goes out; answer honestly after that."""
    self._reads += 1
    if self._reads == 1:
      self[key] = self._cached
    return default if self._reads == 1 else super().get(key, default)


class Within:
  """Calls ``gate.run`` from a :class:`Racer` thread, so a gate that waits forever fails in 5 s.
  For the calls a test makes itself. Calls made from inside a ``discover`` stay where they are:
  being on the same thread as the run they interrupt is what makes them re-entries.
  """

  @staticmethod
  def run(gate: BootstrapGate, discover: Stub) -> ReportMap:
    """Return what ``gate.run`` returned for ``ROOT``, or raise what it raised."""
    return Racer(timeout=5).call(partial(gate.run, ROOT, discover=discover))


def test_first_run_is_cached_and_never_repeated() -> None:
  gate = BootstrapGate()
  report = Runs.report(adapters=('gate_root.Apple',))
  first_run = Stub(report)
  never = Stub.never()

  first = Within.run(gate, first_run)

  assert first == report
  assert Within.run(gate, never) is first
  assert (first_run.calls, never.calls) == (1, 0)


def test_cached_reads_the_cache_without_running_anything() -> None:
  # The facade's warm path: a cached root never builds a discover callable at all.
  gate = BootstrapGate()
  assert gate.cached(ROOT) is None

  first = Within.run(gate, Stub(Runs.report()))

  assert gate.cached(ROOT) is first
  assert gate.cached('another_root') is None
  gate.clear()
  assert gate.cached(ROOT) is None


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

  merged = Within.run(gate, outer)

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
  assert Within.run(gate, Stub.never()) is merged


def test_a_failed_participant_is_left_out_and_the_flight_goes_on() -> None:
  gate = BootstrapGate()
  outer_report = Runs.report(adapters=('gate_root.Apple',))
  failures: list[str] = []

  def stumble() -> None:
    try:
      gate.run(ROOT, discover=Stub(RuntimeError('participant')))
    except RuntimeError as error:
      failures.append(str(error))

  merged = Within.run(gate, Stub(outer_report, before=stumble))

  assert failures == ['participant']
  assert merged == outer_report
  assert Within.run(gate, Stub.never()) is merged


def test_a_failed_owner_caches_nothing_and_its_participants_carry_into_the_retry() -> None:
  gate = BootstrapGate()
  participant_report = Runs.report(adapters=('gate_root.Early',))
  nested_results: list[ReportMap] = []
  owner = Stub(
    RuntimeError('owner'),
    before=lambda: nested_results.append(gate.run(ROOT, discover=Stub(participant_report))),
  )

  with pytest.raises(RuntimeError, match='owner'):
    Within.run(gate, owner)

  # Half a bootstrap is not cached, but Early is registered for good and the retry cannot see it
  # as new, so the retry's report has to inherit it or nobody will ever list it.
  assert nested_results == [participant_report]
  retry = Stub(Runs.report(adapters=('gate_root.Retry',)))
  assert Within.run(gate, retry)['registered_adapters'] == (
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
    Within.run(gate, owner)

  gate.clear()

  retry = Stub(Runs.report(adapters=('gate_root.Retry',)))
  assert Within.run(gate, retry)['registered_adapters'] == ('gate_root.Retry',)


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

  merged = Within.run(gate, outer)

  # Three runs on one thread are three seats: the innermost leaving must not land the flight.
  assert merged['registered_adapters'] == ('gate_root.Inner', 'gate_root.Middle', 'gate_root.Outer')
  assert Within.run(gate, Stub.never()) is merged


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

  racer = Racer(timeout=10)
  with importing.installed():
    racer.start('owner', own)
    racer.start('importer', import_mid_flight)
    racer.join()

  assert racer.raised == {}
  cached = Within.run(gate, Stub.never())
  assert second_call.calls == 0
  assert seen['second'] is cached
  assert cached['registered_adapters'] == ('gate_root.a.Owned', 'gate_root.outside.Late')


def test_concurrent_entry_point_callers_wait_for_one_run_and_share_its_report() -> None:
  gate = BootstrapGate()
  report = Runs.report(adapters=('gate_root.Apple',))
  only_run = Stub(report, before=partial(time.sleep, 0.05))  # keep the flight open for the rest
  barrier = Barrier(8)
  racer = Racer(timeout=10)

  def call() -> ReportMap:
    barrier.wait()
    return gate.run(ROOT, discover=only_run)

  for index in range(8):
    racer.start(f'caller-{index}', call)
  racer.join()

  assert racer.raised == {}
  assert only_run.calls == 1
  assert all(result is racer.results['caller-0'] for result in racer.results.values())
  assert racer.results['caller-0'] == report


def test_owner_failure_wakes_the_waiters_who_each_retry_and_nothing_is_cached() -> None:
  gate = BootstrapGate()
  started, release, owner_failed = Event(), Event(), Event()
  retried_after_failure: list[bool] = []

  def park_owner() -> None:
    started.set()
    release.wait(5)
    owner_failed.set()

  racer = Racer(timeout=10)
  racer.start(
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
    racer.start(name, partial(gate.run, ROOT, discover=stub))
  time.sleep(0.1)  # let the waiters reach the flight; the assertions hold either way
  release.set()
  racer.join()

  assert {name: str(error) for name, error in racer.raised.items()} == {
    'owner': 'owner',
    'waiter-0': 'waiter-0',
    'waiter-1': 'waiter-1',
    'waiter-2': 'waiter-2',
  }
  # Each waiter ran its own discovery exactly once, and only after the owner had failed.
  assert [stub.calls for stub in waiters.values()] == [1, 1, 1]
  assert retried_after_failure == [True, True, True]
  fresh = Stub(Runs.report(adapters=('gate_root.Apple',)))
  assert Within.run(gate, fresh)['registered_adapters'] == ('gate_root.Apple',)
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
      imported: object = importing.run()
    finally:
      participant_left.set()
    return imported

  racer = Racer(timeout=10)
  with importing.installed():
    racer.start('owner', partial(gate.run, ROOT, discover=owner))
    racer.start('importer', import_mid_flight)
    assert owner_started.wait(5)
    for index in range(3):
      racer.start(f'waiter-{index}', partial(gate.run, ROOT, discover=never))
    racer.join()

  assert racer.raised == {}
  cached = Within.run(gate, never)
  assert racer.results['importer'] is participant_report
  assert racer.results['owner'] is cached
  assert all(racer.results[f'waiter-{index}'] is cached for index in range(3))
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
      owned: ReportMap = gate.run(ROOT, discover=Stub(owner_report, before=park_owner))
    finally:
      owner_left.set()
    return owned

  importing = ImportingCall(
    'gate_import_straggler',
    partial(gate.run, ROOT, discover=Stub(participant_report, before=park_participant)),
  )

  def import_mid_flight() -> object:
    owner_started.wait(5)
    return importing.run()

  racer = Racer(timeout=10)
  with importing.installed():
    racer.start('owner', own)
    racer.start('importer', import_mid_flight)
    racer.join()

  assert racer.raised == {}
  cached = Within.run(gate, Stub.never())
  # The owner could not wait for the straggler, so it got the merge so far, uncached.
  assert racer.results['owner'] == owner_report
  assert racer.results['owner'] is not cached
  assert racer.results['importer'] is participant_report
  assert cached['registered_adapters'] == ('gate_root.a.Owned', 'gate_root.outside.Late')


def test_clear_mid_flight_leaves_the_run_in_the_generation_it_started_in() -> None:
  gate = BootstrapGate()
  stale = Stub(Runs.report(adapters=('gate_root.Stale',)), before=gate.clear)
  fresh = Stub(Runs.report(adapters=('gate_root.Fresh',)))

  stale_report = Within.run(gate, stale)
  fresh_report = Within.run(gate, fresh)

  assert stale_report['registered_adapters'] == ('gate_root.Stale',)
  assert fresh_report['registered_adapters'] == ('gate_root.Fresh',)
  assert (stale.calls, fresh.calls) == (1, 1)


def test_a_report_cached_between_the_two_reads_is_returned_not_rediscovered() -> None:
  gate = BootstrapGate()
  cached = Runs.report(adapters=('gate_root.Apple',))
  gate._generation = gate._generation._replace(reports=LateCache(cached))
  never = Stub.never()

  assert Within.run(gate, never) is cached
  assert never.calls == 0


def test_a_keyboard_interrupt_in_the_owner_still_lands_the_flight() -> None:
  # The gate catches BaseException on purpose: an Exception-only handler would leave the flight
  # open after Ctrl-C, and every later caller would wait on it forever. The owner's thread stays
  # alive until the later call is done, because a finished thread may hand its ident to the next
  # one, which would then pass for a re-entry and never wait on the stuck flight at all. Nor can
  # the owner run on the main thread: a regression that never boards would spin it forever.
  gate = BootstrapGate()
  failed, release = Event(), Event()

  def own() -> None:
    try:
      gate.run(ROOT, discover=Stub(KeyboardInterrupt()))
    finally:
      failed.set()
      release.wait(10)

  later = Stub(Runs.report(adapters=('gate_root.Apple',)))
  racer = Racer(timeout=10)
  racer.start('owner', own)
  try:
    assert failed.wait(5)
    landed: ReportMap = Within.run(gate, later)
  finally:
    release.set()
    racer.join()

  assert isinstance(racer.raised['owner'], KeyboardInterrupt)
  assert landed['registered_adapters'] == ('gate_root.Apple',)
  assert later.calls == 1


def test_an_owner_failure_is_not_forgotten_when_a_straggler_leaves_last() -> None:
  # The straggler's clean exit must not wash out the owner's failure, or its partial report would
  # be cached as the whole bootstrap and no retry would ever run.
  gate = BootstrapGate()
  owner_started, joined, owner_left = Event(), Event(), Event()

  def park_owner() -> None:
    owner_started.set()
    joined.wait(5)

  def park_straggler() -> None:
    joined.set()
    owner_left.wait(5)

  importing = ImportingCall(
    'gate_import_failed_owner',
    partial(
      gate.run,
      ROOT,
      discover=Stub(Runs.report(adapters=('gate_root.Late',)), before=park_straggler),
    ),
  )

  def own() -> None:
    try:
      gate.run(ROOT, discover=Stub(RuntimeError('owner'), before=park_owner))
    finally:
      owner_left.set()

  def import_mid_flight() -> object:
    owner_started.wait(5)
    return importing.run()

  racer = Racer(timeout=10)
  with importing.installed():
    racer.start('owner', own)
    racer.start('importer', import_mid_flight)
    racer.join()

  assert {name: str(error) for name, error in racer.raised.items()} == {'owner': 'owner'}
  retry = Stub(Runs.report(adapters=('gate_root.Retry',)))
  assert Within.run(gate, retry)['registered_adapters'] == ('gate_root.Late', 'gate_root.Retry')
  assert retry.calls == 1
