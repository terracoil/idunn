"""One generation of bootstrap memory: what ``BootstrapGate.clear`` throws away whole."""

from __future__ import annotations

from typing import NamedTuple

from idunn.domain import ReportMap

from .bootstrap_flight import BootstrapFlight


class BootstrapGeneration(NamedTuple):
  """Everything ``bootstrap`` remembers, per root: cached reports, flights, carried runs.
  Swapped whole by ``clear()`` and ``restore()``, never emptied: a run captures one at entry, so
  a run that outlives a reset finishes into maps nobody reads, and cannot vouch for registrations
  that the reset already forgot.
  """

  reports: dict[str, ReportMap]  # merged report of each root's finished first bootstrap
  flights: dict[str, BootstrapFlight]  # first bootstraps still in progress
  carried: dict[str, tuple[ReportMap, ...]]  # successful runs of failed flights, for the retry
