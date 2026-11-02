"""Test seams for driving the internal inversion engine.
The public ``Idunn`` facade has no register or resolve, on purpose, which is inconvenient only for
the people testing it. Engine-level tests drive :class:`Wiring` (a standalone mapper and
resolver), ``@Invert()`` integration tests use :class:`Container` to install adapters into the
process singleton, :class:`Resolve` builds a port by hand through the facade's private door,
discovery tests write throwaway packages with :class:`PackageWriter`, and :class:`ImportingCall`
runs a callable as a module body, for tests that need to be mid-import.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
import zipfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from importlib.machinery import ModuleSpec
from pathlib import Path
from textwrap import dedent
from types import ModuleType
from typing import Any

import pytest
from idunn import Idunn
from idunn.domain import ParameterPlan
from idunn.internal import InversionMapper, InversionResolver
from idunn.util import Environment


class Wiring:
  """A standalone engine (own mapper and resolver) with the register/resolve the facade hides."""

  def __init__(self, environment: str | None = None) -> None:
    """Resolve the environment like the facade does (arg → IDUNN_ENV → local)."""
    self.environment: str = Environment.current(environment).name
    self.mapper: InversionMapper = InversionMapper()
    self.resolver: InversionResolver = InversionResolver(self.mapper)

  @property
  def ports(self) -> frozenset[type[Any]]:
    """Ports registered in this engine's catalog."""
    return self.mapper.ports

  def register_adapter(self, adapter: type[Any]) -> bool:
    """Register a ``@Adapter`` class into this engine's catalog."""
    return self.mapper.register_adapter(adapter)

  def register_port(self, port: type[Any]) -> bool:
    """Register a ``@Port`` Protocol into this engine's catalog."""
    return self.mapper.register_port(port)

  def resolve(self, port: type[Any], *, key: str | None = None) -> Any:
    """Resolve a port into an adapter instance for this engine's environment."""
    return self.resolver.inject(parameter=Resolve.required(port, key), environment=self.environment)


class Container:
  """Installs adapters into the process-wide ``Idunn()`` singleton that ``@Invert`` reads."""

  @staticmethod
  def install(*adapters: type[Any]) -> None:
    """Register the adapters into the singleton's catalog as one batch: all of them, or none."""
    Idunn()._mapper.register_batch(adapters=adapters)


class Resolve:
  """Resolves a port by hand through the facade's one private door, as a required parameter."""

  @staticmethod
  def port(port: type[Any], key: str | None = None) -> Any:
    """Build ``port``'s adapter in the singleton's environment; raise as a required port would."""
    return Idunn()._inject(Resolve.required(port, key))

  @staticmethod
  def required(port: type[Any], key: str | None = None) -> ParameterPlan:
    """Plan ``port`` with no default and no ``| None``, so a missing adapter raises."""
    return ParameterPlan(name='port', port=port, key=key, optional=False)


class ImportingCall(importlib.abc.MetaPathFinder, importlib.abc.Loader):
  """Runs ``body`` as the body of a made-up module, so it runs inside a real ``import``.
  It is its own finder and loader, so ``body`` runs from ``exec_module`` with no module-body
  frame at all, just like a C extension's init, which is the hardest case for import detection.
  """

  def __init__(self, name: str, body: Callable[[], object]) -> None:
    """Answer imports of ``name`` (and nothing else) by calling ``body``."""
    self.name: str = name
    self.result: object = None
    self._body: Callable[[], object] = body

  def create_module(self, spec: ModuleSpec) -> ModuleType | None:
    """Let ``importlib`` build an ordinary empty module."""
    return None

  def exec_module(self, module: ModuleType) -> None:
    """Run the body and keep what it returned."""
    self.result = self._body()

  def find_spec(
    self,
    fullname: str,
    path: Sequence[str] | None,
    target: ModuleType | None = None,
  ) -> ModuleSpec | None:
    """Claim only this call's module name."""
    return importlib.util.spec_from_loader(fullname, self) if fullname == self.name else None

  @contextmanager
  def installed(self) -> Iterator[ImportingCall]:
    """Put this finder first on ``sys.meta_path`` for the block, then remove it and its module."""
    sys.meta_path.insert(0, self)
    try:
      yield self
    finally:
      sys.meta_path.remove(self)
      sys.modules.pop(self.name, None)

  def run(self) -> object:
    """Import the module, which runs ``body`` mid-import, and return what it returned."""
    importlib.import_module(self.name)
    return self.result


class PackageWriter:
  """Writes throwaway packages under ``tmp_path`` and puts them on ``sys.path``."""

  def __init__(self, *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remember where to write; ``monkeypatch`` undoes the ``sys.path`` change after the test."""
    self._tmp_path: Path = tmp_path
    self._monkeypatch: pytest.MonkeyPatch = monkeypatch

  def module(self, name: str, source: str) -> None:
    """Write a single top-level module ``<name>.py`` (a root with no ``__path__``)."""
    (self._tmp_path / f'{name}.py').write_text(self._text(source), encoding='utf-8')
    self._activate()

  def package(self, name: str, files: dict[str, str]) -> Path:
    """Write package ``name`` from ``files`` (relative path to source); return its directory.
    Every directory gets an empty ``__init__.py`` unless ``files`` supplies one or its name ends
    in ``_ns``, which keeps it a namespace package.
    """
    package_dir: Path = self._tmp_path / name
    package_dir.mkdir()
    for relative_path, source in files.items():
      path: Path = package_dir / relative_path
      path.parent.mkdir(parents=True, exist_ok=True)
      path.write_text(self._text(source), encoding='utf-8')
    for directory in (package_dir, *(p for p in package_dir.rglob('*') if p.is_dir())):
      init: Path = directory / '__init__.py'
      if not directory.name.endswith('_ns') and not init.exists():
        init.write_text('', encoding='utf-8')
    self._activate()
    return package_dir

  def zipped_package(self, name: str, files: dict[str, str]) -> Path:
    """Write package ``name`` into ``<name>.zip`` and put the archive itself on ``sys.path``.
    Python imports it happily through ``zipimport``; discovery, which reads directories, should
    refuse it out loud. ``files`` must supply every ``__init__.py`` it wants.
    """
    archive: Path = self._tmp_path / f'{name}.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
      for relative_path, source in files.items():
        bundle.writestr(f'{name}/{relative_path}', self._text(source))
    self._monkeypatch.syspath_prepend(str(archive))
    importlib.invalidate_caches()
    return archive

  def _activate(self) -> None:
    self._monkeypatch.syspath_prepend(str(self._tmp_path))
    importlib.invalidate_caches()

  @staticmethod
  def _text(source: str) -> str:
    return dedent(source).strip() + '\n' if source.strip() else ''
