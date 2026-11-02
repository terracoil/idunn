"""Fold the reports of several discovery runs of one root into one."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import chain

from idunn.domain import ReportMap


class ReportMerger:
  """Merges the runs of one root's first ``bootstrap`` into the report that gets cached.
  Several runs happen when a module calls ``bootstrap`` while it is being imported, in this thread
  or another. Each run reports only what *it* newly registered, and registration is atomic and
  idempotent, so every class is new for exactly one run: concatenating the ``registered_*`` tuples
  is exact, with nothing missing and nothing listed twice.
  """

  @staticmethod
  def merge(reports: Sequence[ReportMap]) -> ReportMap:
    """Return one report covering every run in ``reports``, given in the order the runs finished.
    ``imported_modules`` is the sorted union. A module some run skipped but another imported is
    not skipped, it was merely early. ``registered_*`` keep run-finish order. There is always at
    least one report, the run that just finished, so the root name comes from the first.
    """
    imported: frozenset[str] = frozenset(
      chain.from_iterable(report['imported_modules'] for report in reports)
    )
    skipped: frozenset[str] = frozenset(
      chain.from_iterable(report['skipped_modules'] for report in reports)
    )
    return {
      'root_package': reports[0]['root_package'],
      'imported_modules': tuple(sorted(imported)),
      'skipped_modules': tuple(sorted(skipped - imported)),
      'registered_ports': tuple(
        chain.from_iterable(report['registered_ports'] for report in reports)
      ),
      'registered_adapters': tuple(
        chain.from_iterable(report['registered_adapters'] for report in reports)
      ),
    }
