"""Bounded discovery for decorated Idunn ports and adapters."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from types import ModuleType
from typing import Any

from idunn.domain import DiscoveryError, ReportMap
from idunn.util import QualifiedName

from .inversion_mapper import InversionMapper


class AutoDiscovery:
  """Imports bounded port/adapter modules and registers decorated classes."""

  DEFAULT_PORT_PACKAGE_NAMES = frozenset({'port', 'ports'})
  DEFAULT_ADAPTER_PACKAGE_NAMES = frozenset({'adapter', 'adapters'})

  def autodiscover(
    self,
    *,
    mapper: InversionMapper,
    root_package: str | ModuleType,
    port_package_names: frozenset[str] | None = None,
    adapter_package_names: frozenset[str] | None = None,
    strict: bool = True,
  ) -> ReportMap:
    """Discover decorated ports first, then decorated adapters."""
    normalized_port_names = self._normalized_names(
      names=port_package_names,
      fallback=self.DEFAULT_PORT_PACKAGE_NAMES,
    )
    normalized_adapter_names = self._normalized_names(
      names=adapter_package_names,
      fallback=self.DEFAULT_ADAPTER_PACKAGE_NAMES,
    )
    root_module = self._import_root(root_package=root_package)
    port_module_names = self._candidate_module_names(
      root_module=root_module,
      package_names=normalized_port_names,
    )
    adapter_module_names = self._candidate_module_names(
      root_module=root_module,
      package_names=normalized_adapter_names,
    )
    port_modules = self._import_modules(
      module_names=port_module_names,
      strict=strict,
      module_kind='port',
    )
    registered_ports = self._register_decorated_ports(mapper=mapper, modules=port_modules)
    adapter_modules = self._import_modules(
      module_names=adapter_module_names,
      strict=strict,
      module_kind='adapter',
    )
    additional_ports = self._register_decorated_ports(mapper=mapper, modules=adapter_modules)
    registered_adapters = self._register_decorated_adapters(
      mapper=mapper,
      modules=adapter_modules,
    )
    imported_port_modules = tuple(module.__name__ for module in port_modules)
    imported_adapter_modules = tuple(module.__name__ for module in adapter_modules)
    return {
      'root_package': root_module.__name__,
      'imported_port_modules': imported_port_modules,
      'imported_adapter_modules': imported_adapter_modules,
      'imported_modules': (*imported_port_modules, *imported_adapter_modules),
      'registered_ports': tuple(
        QualifiedName.of(cls) for cls in (*registered_ports, *additional_ports)
      ),
      'registered_adapters': tuple(QualifiedName.of(cls) for cls in registered_adapters),
    }

  def _normalized_names(
    self,
    *,
    names: frozenset[str] | None,
    fallback: frozenset[str],
  ) -> frozenset[str]:
    source = names if names is not None else fallback
    return frozenset(item.lower() for item in source)

  def _import_root(self, *, root_package: str | ModuleType) -> ModuleType:
    return importlib.import_module(root_package) if isinstance(root_package, str) else root_package

  def _candidate_module_names(
    self,
    *,
    root_module: ModuleType,
    package_names: frozenset[str],
  ) -> tuple[str, ...]:
    names: list[str] = []
    if self._has_named_part(module_name=root_module.__name__, package_names=package_names):
      names.append(root_module.__name__)

    root_path = getattr(root_module, '__path__', None)
    if root_path is not None:
      for path_entry in root_path:
        names.extend(
          self._candidate_module_names_from_path(
            root_module=root_module,
            root_path=Path(path_entry),
            package_names=package_names,
          )
        )

    return tuple(dict.fromkeys(sorted(names)))

  def _candidate_module_names_from_path(
    self,
    *,
    root_module: ModuleType,
    root_path: Path,
    package_names: frozenset[str],
  ) -> tuple[str, ...]:
    names: list[str] = []
    if root_path.exists():
      for python_file in root_path.rglob('*.py'):
        module_name = self._module_name_for_file(
          root_module=root_module,
          root_path=root_path,
          python_file=python_file,
        )
        if self._has_named_part(module_name=module_name, package_names=package_names):
          names.append(module_name)
    return tuple(names)

  def _module_name_for_file(
    self,
    *,
    root_module: ModuleType,
    root_path: Path,
    python_file: Path,
  ) -> str:
    relative_path = python_file.relative_to(root_path)
    parts = list(relative_path.with_suffix('').parts)
    if parts[-1] == '__init__':
      parts = parts[:-1]
    dotted_suffix = '.'.join(parts)
    return f'{root_module.__name__}.{dotted_suffix}' if dotted_suffix else root_module.__name__

  def _has_named_part(self, *, module_name: str, package_names: frozenset[str]) -> bool:
    parts = module_name.split('.')
    return bool(set(parts).intersection(package_names))

  def _import_modules(
    self,
    *,
    module_names: tuple[str, ...],
    strict: bool,
    module_kind: str,
  ) -> tuple[ModuleType, ...]:
    modules: list[ModuleType] = []
    for module_name in module_names:
      try:
        modules.append(importlib.import_module(module_name))
      except Exception as exc:  # noqa: BLE001
        if strict:
          message = f'Idunn failed to import {module_kind} module {module_name!r}: {exc}'
          raise DiscoveryError(message) from exc
        # non-strict: skip the unimportable module and continue discovery
    return tuple(modules)

  def _register_decorated_ports(
    self,
    *,
    mapper: InversionMapper,
    modules: tuple[ModuleType, ...],
  ) -> tuple[type[Any], ...]:
    registered: list[type[Any]] = []
    for module in modules:
      for candidate in self._decorated_classes(module=module, marker='__idunn_port__'):
        if mapper.register_port(candidate):
          registered.append(candidate)
    return tuple(registered)

  def _register_decorated_adapters(
    self,
    *,
    mapper: InversionMapper,
    modules: tuple[ModuleType, ...],
  ) -> tuple[type[Any], ...]:
    registered: list[type[Any]] = []
    for module in modules:
      for candidate in self._decorated_classes(module=module, marker='__idunn_adapter__'):
        if mapper.register_adapter(candidate):
          registered.append(candidate)
    return tuple(registered)

  def _decorated_classes(self, *, module: ModuleType, marker: str) -> tuple[type[Any], ...]:
    # Own-__dict__ check: an adapter subclassing its port *inherits* __idunn_port__,
    # so getattr would mis-detect adapters as ports. The flag lives on the decorated class only.
    return tuple(
      candidate
      for _, candidate in inspect.getmembers(module, inspect.isclass)
      if candidate.__module__ == module.__name__ and marker in candidate.__dict__
    )
