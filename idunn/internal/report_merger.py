"""Fold the reports of several discovery runs of one root into one."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from itertools import chain
from typing import Literal, TypeAlias

from idunn.domain import ReportMap

# The report's tuple-of-names fields: a Literal, since a TypedDict is read by literal key only.
Field: TypeAlias = Literal[
  'imported_modules', 'skipped_modules', 'registered_ports', 'registered_adapters'
]


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
    imported: frozenset[str] = frozenset(ReportMerger._joined(reports, 'imported_modules'))
    skipped: frozenset[str] = frozenset(ReportMerger._joined(reports, 'skipped_modules'))
    return {
      'root_package': reports[0]['root_package'],
      'imported_modules': tuple(sorted(imported)),
      'skipped_modules': tuple(sorted(skipped - imported)),
      'registered_ports': tuple(ReportMerger._joined(reports, 'registered_ports')),
      'registered_adapters': tuple(ReportMerger._joined(reports, 'registered_adapters')),
    }

  @staticmethod
  def _joined(reports: Sequence[ReportMap], field: Field) -> Iterator[str]:
    return chain.from_iterable(report[field] for report in reports)
