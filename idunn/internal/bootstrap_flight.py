"""One root's first ``bootstrap`` while it is still in progress."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from threading import Event, get_ident

from idunn.domain import ReportMap


@dataclass(frozen=True, slots=True)
class BootstrapFlight:
  """The runs of one root's first ``bootstrap`` that have not all finished yet.
  Frozen and replaced whole under :class:`BootstrapGate`'s lock, so a thread holding an old copy
  holds a consistent one. The ``done`` event is the one shared, mutable part: it is set once, by
  whichever run finishes last, and wakes every caller that chose to wait rather than discover.
  ``runners`` records the thread of every run still going, one entry per run, so a re-entry
  nested three deep is three entries. Asking "does this thread have a run aboard?" rather than
  "did this thread open the flight?" is what keeps a finished owner, or a new thread that
  inherited its ident, from mistaking an entry-point call for a re-entry.
  """

  runners: tuple[int, ...]  # thread idents of the runs in progress, one entry per run
  done: Event = field(default_factory=Event, compare=False)
  reports: tuple[ReportMap, ...] = ()  # finished runs' reports, in finish order
  failed: bool = False  # the owner's run raised: cache nothing, carry the reports to the retry

  @classmethod
  def launch(cls, *, carried: tuple[ReportMap, ...] = ()) -> BootstrapFlight:
    """Open a flight for this thread's run, starting from a failed flight's ``carried`` reports.
    Those runs registered their classes for good, so no retry will ever report them as new; the
    flight has to remember them or the cached report never will.
    """
    return cls(runners=(get_ident(),), reports=carried)

  def aboard_here(self) -> bool:
    """Report whether this thread has a run aboard, so waiting would mean waiting on itself."""
    return get_ident() in self.runners

  def boarded(self) -> BootstrapFlight:
    """Return this flight with one more run in progress, on the calling thread."""
    return replace(self, runners=(*self.runners, get_ident()))

  @property
  def landed(self) -> bool:
    """``True`` once every run has finished, so the last one out may close the flight."""
    return not self.runners

  def leaving(self, *, report: ReportMap | None, owner_failed: bool) -> BootstrapFlight:
    """Return this flight with the calling thread's innermost run finished.
    ``report`` is that run's report, or ``None`` if it raised. A run always leaves on the thread it
    boarded on, so removing one entry for this thread removes the right one.
    """
    return replace(
      self,
      runners=self._without_one(get_ident()),
      reports=self.reports if report is None else (*self.reports, report),
      failed=self.failed or owner_failed,
    )

  def _without_one(self, ident: int) -> tuple[int, ...]:
    # One entry, not all of them: the outer runs of a nested re-entry are still going.
    index: int = self.runners.index(ident)
    return (*self.runners[:index], *self.runners[index + 1 :])
