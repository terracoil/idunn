"""Typed structure returned by Idunn autodiscovery."""

from __future__ import annotations

from typing import TypedDict


class ReportMap(TypedDict):
  """Summary of one autodiscovery run: modules imported and classes registered.

  ``registered_ports`` / ``registered_adapters`` hold fully-qualified class
  names (``module.QualName``), not class objects, so the report stays a plain
  serialisable dict of strings.
  """

  root_package: str
  imported_port_modules: tuple[str, ...]
  imported_adapter_modules: tuple[str, ...]
  imported_modules: tuple[str, ...]
  registered_ports: tuple[str, ...]
  registered_adapters: tuple[str, ...]
