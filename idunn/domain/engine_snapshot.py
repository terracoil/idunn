"""The engine's state at one moment, so a test block can put it back exactly as it found it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .catalog import Catalog, SlotKey
from .report import ReportMap


@dataclass(frozen=True, slots=True)
class EngineSnapshot:
  """Everything a ``Harness`` block can change, taken on entry and put back on exit.
  The catalog and the overrides are immutable already, so they are kept by reference. The rest is
  copied on the way in and must be copied again on the way out: a restore that installed these
  very mappings would let the next singleton or report write straight into the snapshot, and an
  outer block would then "restore" whatever an inner one leaked. They sit behind read-only proxies
  so that mistake fails loudly instead of quietly. Bootstrap memory is part of the picture because
  a report outliving its rolled-back registrations would leave ``bootstrap`` sure it had nothing
  left to do.
  """

  environment: str  # a reset() inside the block rebinds it, and the exit undoes that too
  catalog: Catalog
  instances: Mapping[type[Any], Any]  # built singletons, per adapter class
  overrides: Mapping[SlotKey, object]  # stand-ins answering a (port, key) ahead of selection
  reports: Mapping[str, ReportMap]  # bootstrap's cached reports, per root
  carried: Mapping[str, tuple[ReportMap, ...]]  # successful runs of failed flights, per root
