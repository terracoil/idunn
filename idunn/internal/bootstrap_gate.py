"""Once-per-root discovery that never holds a lock across an import."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from threading import Lock
from types import MappingProxyType

from idunn.domain import ReportMap
from idunn.util import ImportContext

from .bootstrap_flight import BootstrapFlight
from .bootstrap_generation import BootstrapGeneration
from .report_merger import ReportMerger


class BootstrapGate:
  """Runs a root's discovery once, caches the merged report, and stays out of import's way.
  Two rules keep it deadlock-free. No lock of the gate's is held while modules import: the lock
  guards bookkeeping only. And a thread that may be holding an import lock (an ``import`` on its
  stack, see :class:`~idunn.util.ImportContext`) never waits for another thread's discovery; it
  joins the flight and discovers itself, and ``importlib`` arbitrates the module locks as it
  would for any two importers. Entry-point callers that find a flight in progress wait for it
  instead, which is what makes concurrent first calls share one report. Every run of the root's
  first bootstrap is merged into that report by whichever run finishes last, failed flights'
  successful runs included, because what they registered stays registered.
  """

  def __init__(self) -> None:
    """Start with nothing cached and nothing in flight."""
    self._lock: Lock = Lock()
    self._generation: BootstrapGeneration = BootstrapGeneration(reports={}, flights={}, carried={})

  def cached(self, root_package: str) -> ReportMap | None:
    """Return the report cached for ``root_package``, or ``None``; one lock-free dictionary read.
    The warm path for callers that would otherwise build a ``discover`` callable just to be told
    the answer was already here, which ``@Invert(bootstrap=...)`` asks on every call.
    """
    return self._generation.reports.get(root_package)

  def clear(self) -> None:
    """Forget every cached report. Runs still in flight finish into the generation they started in.
    Swapping the maps, rather than emptying them, is what lets a stale run land somewhere harmless.
    """
    with self._lock:
      self._generation = BootstrapGeneration(reports={}, flights={}, carried={})

  def restore(
    self,
    *,
    reports: Mapping[str, ReportMap],
    carried: Mapping[str, tuple[ReportMap, ...]],
  ) -> None:
    """Swap in a new generation holding copies of what :meth:`snapshot` returned.
    Flights start empty, as after :meth:`clear`: a run still in flight finishes into the discarded
    generation, and copying keeps later runs from writing into the snapshot itself.
    """
    with self._lock:
      self._generation = BootstrapGeneration(
        reports=dict(reports), flights={}, carried=dict(carried)
      )

  def run(self, root_package: str, *, discover: Callable[[], ReportMap]) -> ReportMap:
    """Return the cached report for ``root_package``, running ``discover`` if this call must.
    A call that joins a flight already in progress (a re-entry, or a call made during an import)
    returns its own run's report, since it could not wait for anyone else's. Every other call gets
    the merged report: the cached one, unless an import-time straggler outlived the owner. A failed
    first run caches nothing and wakes its waiters, who try again themselves; the runs that did
    succeed carry over into the retry's report.
    """
    generation: BootstrapGeneration = self._generation  # one read: a reset() cannot split it
    reports: dict[str, ReportMap] = generation.reports
    report: ReportMap | None = reports.get(root_package)
    while report is None:
      with self._lock:
        report = reports.get(root_package)
        flight: BootstrapFlight | None = generation.flights.get(root_package)
        boarding: bool = report is None and self._may_board(flight)
        if boarding:
          generation.flights[root_package] = (
            BootstrapFlight.launch(carried=generation.carried.pop(root_package, ()))
            if flight is None
            else flight.boarded()
          )
      if boarding:
        report = self._take_part(
          generation=generation,
          root_package=root_package,
          discover=discover,
          owner=flight is None,
        )
      elif report is None and flight is not None:  # not boarding means a flight; this narrows it
        flight.done.wait()  # holds no gate lock, and no import lock, or it would have boarded
        report = reports.get(root_package)  # still None if the owner failed: go round and claim
    return report

  def snapshot(self) -> tuple[Mapping[str, ReportMap], Mapping[str, tuple[ReportMap, ...]]]:
    """Return read-only copies of the cached reports and the carried runs, from one generation.
    Flights are left out: a run in progress belongs to whoever started it, not to a snapshot.
    """
    with self._lock:
      generation: BootstrapGeneration = self._generation
      memory: tuple[Mapping[str, ReportMap], Mapping[str, tuple[ReportMap, ...]]] = (
        MappingProxyType(dict(generation.reports)),
        MappingProxyType(dict(generation.carried)),
      )
    return memory

  def _leave(
    self,
    *,
    generation: BootstrapGeneration,
    root_package: str,
    report: ReportMap | None,
    owner_failed: bool,
  ) -> BootstrapFlight:
    # The last run out caches the merge and wakes the waiters. Nobody waits for that to happen,
    # so finishing order costs no deadlock edge. A failed flight caches nothing, but its successful
    # runs registered for good and no retry will see their classes as new, so they carry over.
    flights: dict[str, BootstrapFlight] = generation.flights
    with self._lock:
      flight: BootstrapFlight = flights[root_package].leaving(
        report=report, owner_failed=owner_failed
      )
      if flight.landed:
        del flights[root_package]
        if flight.failed:
          generation.carried[root_package] = flight.reports
        else:
          generation.reports[root_package] = ReportMerger.merge(flight.reports)
        flight.done.set()
      else:
        flights[root_package] = flight
    return flight

  @staticmethod
  def _may_board(flight: BootstrapFlight | None) -> bool:
    # Board when there is no flight to wait for, when this thread already has a run aboard (a
    # re-entry, which would otherwise wait on itself), or when it may hold an import lock that a
    # run in the flight needs.
    return flight is None or flight.aboard_here() or ImportContext.active()

  def _take_part(
    self,
    *,
    generation: BootstrapGeneration,
    root_package: str,
    discover: Callable[[], ReportMap],
    owner: bool,
  ) -> ReportMap:
    # Only the owner's failure fails the flight: a participant's error is its caller's problem,
    # and the runs that did succeed still registered what they found.
    try:
      own: ReportMap = discover()
    except BaseException:
      self._leave(generation=generation, root_package=root_package, report=None, owner_failed=owner)
      raise
    flight: BootstrapFlight = self._leave(
      generation=generation, root_package=root_package, report=own, owner_failed=False
    )
    # The owner hands back the cached merge whenever it closed the flight. Only a run that joined
    # from an import the owner never waits on (a module outside the root, or one it excludes or
    # skips) can outlive it; then the owner gets the merge so far and the straggler caches the rest.
    answer: ReportMap | None = generation.reports.get(root_package) if owner else own
    return ReportMerger.merge(flight.reports) if answer is None else answer
