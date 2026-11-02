"""Discovery of every decorated port and adapter under one root package."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Iterable
from fnmatch import fnmatchcase
from pathlib import Path
from types import ModuleType
from typing import Any

from idunn.domain import DiscoveryError, ReportMap
from idunn.util import QualifiedName

from .inversion_mapper import InversionMapper
from .port_registry import PortRegistry


class AutoDiscovery:
  """Import every module under a root package, then register its decorated classes.
  Every import finishes before anything registers, so a strict import failure leaves the catalog
  exactly as it was. Discovery walks the file system, so a root that does not live in directories
  (a zip, an egg, some frozen bundles) is refused outright rather than half-scanned.
  """

  # Matched against each dotted part *below* the root, so a test package named as the root is
  # still scanned on purpose. User patterns add to these; they never replace them.
  DEFAULT_EXCLUDE: frozenset[str] = frozenset({'tests', 'test', 'test_*', '*_test', 'conftest'})

  # Importing ``pkg.__main__`` runs the package's CLI, so it is never a discovery target.
  NEVER_IMPORTED: frozenset[str] = frozenset({'__main__'})

  def autodiscover(
    self,
    *,
    mapper: InversionMapper,
    root_package: str,
    exclude: Iterable[str] | str = (),
    strict: bool = True,
  ) -> ReportMap:
    """Import all modules under the dotted ``root_package`` first, then ports, then adapters.
    A non-directory ``__path__`` entry raises :class:`DiscoveryError` whatever ``strict`` says:
    there is no module to name in ``skipped_modules``, and a root that cannot be scanned is a
    configuration error, not an unlucky import.
    """
    # Outside the strict handling: a root that will not import raises its own error regardless.
    root_module = importlib.import_module(root_package)
    module_names = self._module_names(root_module=root_module, patterns=self._patterns(exclude))
    modules, skipped = self._import_modules(module_names=module_names, strict=strict)
    # Ports before adapters across the whole set: an adapter registers its port implicitly,
    # which would hide that port from the report if it came first.
    registered_ports = self._register_matching(
      modules=modules, matches=PortRegistry.is_port, register=mapper.register_port
    )
    registered_adapters = self._register_matching(
      modules=modules, matches=self._is_adapter, register=mapper.register_adapter
    )
    return {
      'root_package': root_module.__name__,
      'imported_modules': tuple(module.__name__ for module in modules),
      'skipped_modules': skipped,
      'registered_ports': registered_ports,
      'registered_adapters': registered_adapters,
    }

  def _defined_classes(self, *, module: ModuleType) -> tuple[type[Any], ...]:
    # Each class is attributed to the one module that defines it: re-exports are not counted
    # twice, and classes imported from outside the root are never registered through it.
    return tuple(
      candidate
      for candidate in vars(module).values()
      if isinstance(candidate, type) and candidate.__module__ == module.__name__
    )

  def _import_modules(
    self,
    *,
    module_names: tuple[str, ...],
    strict: bool,
  ) -> tuple[tuple[ModuleType, ...], tuple[str, ...]]:
    modules: list[ModuleType] = []
    skipped: list[str] = []
    for module_name in module_names:
      try:
        modules.append(self._load(module_name=module_name))
      except Exception as exc:  # any import failure counts; SystemExit still gets through
        if strict:
          message = f'Idunn failed to import module {module_name!r}: {exc}'
          raise DiscoveryError(message) from exc
        skipped.append(module_name)
    return tuple(modules), tuple(skipped)

  def _is_adapter(self, candidate: type[Any]) -> bool:
    # Own __dict__, not getattr: a subclass inherits the flag without wearing the decorator.
    return '__idunn_adapter__' in candidate.__dict__

  def _is_excluded(self, *, relative_parts: tuple[str, ...], patterns: frozenset[str]) -> bool:
    return any(
      not part.isidentifier()
      or part in self.NEVER_IMPORTED
      or any(fnmatchcase(part, pattern) for pattern in patterns)
      for part in relative_parts
    )

  def _load(self, *, module_name: str) -> ModuleType:
    # ``python -m pkg.main`` runs pkg.main as ``__main__``; importing it by name would build a
    # second copy whose classes the running script never sees, so scan the running module.
    running: ModuleType | None = sys.modules.get('__main__')
    running_name: str | None = getattr(getattr(running, '__spec__', None), 'name', None)
    is_running: bool = running is not None and running_name == module_name
    return running if is_running and running is not None else importlib.import_module(module_name)

  def _module_names(self, *, root_module: ModuleType, patterns: frozenset[str]) -> tuple[str, ...]:
    # Every .py under every __path__ entry counts, directories without __init__.py included.
    names: set[str] = {root_module.__name__}
    for path_entry in self._path_entries(root_module=root_module):
      for python_file in path_entry.rglob('*.py'):
        relative_parts = self._relative_parts(root_path=path_entry, python_file=python_file)
        if relative_parts and not self._is_excluded(
          relative_parts=relative_parts, patterns=patterns
        ):
          names.add('.'.join((root_module.__name__, *relative_parts)))
    return tuple(sorted(names))

  def _path_entries(self, *, root_module: ModuleType) -> tuple[Path, ...]:
    # rglob on a zip member path finds nothing and says nothing; better to say something.
    entries: tuple[Path, ...] = tuple(Path(entry) for entry in getattr(root_module, '__path__', ()))
    unscannable: list[str] = [str(entry) for entry in entries if not entry.is_dir()]
    if unscannable:
      message = (
        f'Idunn cannot scan package {root_module.__name__!r}: no directory at '
        f'{", ".join(unscannable)} (a zip, egg or frozen bundle?). Discovery reads the file '
        'system, so install the package unpacked.'
      )
      raise DiscoveryError(message)
    return entries

  def _patterns(self, exclude: Iterable[str] | str) -> frozenset[str]:
    extra: Iterable[str] = (exclude,) if isinstance(exclude, str) else exclude
    return self.DEFAULT_EXCLUDE | frozenset(extra)

  def _register_matching(
    self,
    *,
    modules: tuple[ModuleType, ...],
    matches: Callable[[type[Any]], bool],
    register: Callable[[type[Any]], bool],
  ) -> tuple[str, ...]:
    registered: list[str] = []
    for module in modules:
      for candidate in filter(matches, self._defined_classes(module=module)):
        if register(candidate):
          registered.append(QualifiedName.of(candidate))
    return tuple(registered)

  def _relative_parts(self, *, root_path: Path, python_file: Path) -> tuple[str, ...]:
    parts = python_file.relative_to(root_path).with_suffix('').parts
    return parts[:-1] if parts[-1] == '__init__' else parts
