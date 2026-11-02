"""The typed report that discovery returns."""

from __future__ import annotations

from typing import TypedDict


class ReportMap(TypedDict):
  """Summary of one discovery run: what it imported and what it newly registered.
  ``imported_modules`` and ``skipped_modules`` hold dotted module names; ``skipped_modules`` stays
  empty unless ``strict=False`` let discovery step over modules that failed to import.
  ``registered_ports`` and ``registered_adapters`` list only the classes *this call* registered,
  so a repeat run reports none; for ``bootstrap``, the cached report merges every run of the root's
  first bootstrap, the successful runs of any failed attempt before it included, so it lists
  everything that bootstrap registered. They hold ``module.QualName`` strings rather than class
  objects, which keeps the report a plain dict you can log or serialize without a second thought.
  """

  root_package: str
  imported_modules: tuple[str, ...]  # sorted; includes the root itself
  skipped_modules: tuple[str, ...]
  registered_ports: tuple[str, ...]
  registered_adapters: tuple[str, ...]
