"""Test seams for driving the internal inversion engine.

Resolution and manual registration are no longer on the public ``Idunn`` facade, so
engine-level tests drive :class:`Wiring` (a standalone mapper+resolver), and ``@Invert``
integration tests use :class:`Container` to install adapters into the process singleton.
Discovery tests write throwaway packages with :class:`PackageWriter`.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest
from idunn import Idunn
from idunn.internal import InversionMapper, InversionResolver
from idunn.util import Environment


class Wiring:
  """A standalone engine (own mapper + resolver) mirroring the facade's register/resolve."""

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
    return self.resolver.resolve(port=port, key=key, environment=self.environment)


class Container:
  """Installs adapters into the process-wide ``Idunn()`` singleton that ``@Invert`` reads."""

  @staticmethod
  def install(*adapters: type[Any]) -> None:
    """Register each adapter into the singleton's catalog."""
    mapper = Idunn()._mapper
    for adapter in adapters:
      mapper.register_adapter(adapter)


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

    Every directory gets an empty ``__init__.py`` unless ``files`` supplies one, except
    directories whose name ends in ``_ns``, which stay namespace packages.
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

  def _activate(self) -> None:
    self._monkeypatch.syspath_prepend(str(self._tmp_path))
    importlib.invalidate_caches()

  @staticmethod
  def _text(source: str) -> str:
    return dedent(source).strip() + '\n' if source.strip() else ''
