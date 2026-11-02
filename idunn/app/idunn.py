"""Idunn: the process-wide facade over the inversion engine."""

from __future__ import annotations

from collections.abc import Iterable
from threading import RLock
from typing import Any

from idunn.domain import AdapterMetadata, LifecycleEnum, PortBinding, ReportMap
from idunn.internal import AutoDiscovery, InversionMapper, InversionResolver
from idunn.util import Environment, MetaSingleton, QualifiedName


class Idunn(metaclass=MetaSingleton):
  """Process-wide singleton facade: discover a graph, then let ``@Invert`` wire it.

  ``Idunn()`` always returns the same instance. Application code touches it exactly
  once — ``autodiscover()`` at startup, or ``bootstrap()`` lazily from a library's
  entry points (plus ``reset()`` for test isolation); everything else (registration,
  selection, construction) lives behind it in
  :class:`~idunn.internal.InversionMapper` / :class:`~idunn.internal.InversionResolver`.
  """

  def __init__(self, *, environment: str | None = None) -> None:
    """Bind to the resolved environment and create an empty engine."""
    self._environment: str = Environment.current(environment).name
    self._mapper: InversionMapper = InversionMapper()
    self._resolver: InversionResolver = InversionResolver(self._mapper)
    self._bootstrap_lock: RLock = RLock()
    self._bootstrapped: dict[str, ReportMap] = {}

  def autodiscover(
    self,
    root_package: str,
    *,
    exclude: Iterable[str] | str = (),
    strict: bool = True,
  ) -> ReportMap:
    """Import every module under ``root_package`` and register its decorated classes.

    Test modules (``tests``, ``test``, ``test_*``, ``*_test``, ``conftest``), any ``__main__``
    and every ``exclude`` pattern are skipped; patterns match each dotted part below the root.
    """
    return AutoDiscovery().autodiscover(
      mapper=self._mapper,
      root_package=root_package,
      exclude=exclude,
      strict=strict,
    )

  def bootstrap(
    self,
    root_package: str,
    *,
    exclude: Iterable[str] | str = (),
    strict: bool = True,
  ) -> ReportMap:
    """Run ``autodiscover`` for ``root_package`` at most once per process.

    Meant for libraries that cannot rely on a startup hook: call it from every public
    entry point (a decorator, a classmethod, a ``__new__``) and the graph is wired on
    first use rather than at import. The first call for a root performs the discovery
    with the options given; later calls for the same root return the cached
    :class:`~idunn.ReportMap` without rescanning, and their options are ignored.
    Distinct roots are discovered independently. Thread-safe and re-entrant: a bootstrap
    triggered by a module that an in-progress discovery is importing does not deadlock.
    ``reset()`` forgets the cache along with the registrations.
    """
    if root_package not in self._bootstrapped:
      with self._bootstrap_lock:
        if root_package not in self._bootstrapped:
          report = self.autodiscover(root_package, exclude=exclude, strict=strict)
          # A re-entered bootstrap (nested call during discovery) caches first; keep its
          # report, which lists the registrations, rather than the outer, emptier one.
          self._bootstrapped.setdefault(root_package, report)
    return self._bootstrapped[root_package]

  def describe(self) -> str:
    """Return a readable snapshot of the active port→adapter bindings."""
    lines = [f'Environment: {self._environment}']
    for binding in self._mapper.bindings(environment=self._environment):
      lines.extend(self._describe_binding(binding=binding))
    return '\n'.join(lines)

  @property
  def environment(self) -> str:
    """Active environment used for adapter filtering."""
    return self._environment

  def reset(self, *, environment: str | None = None) -> Idunn:
    """Clear all registrations, instances and bootstrap memory; rebind the environment."""
    self._environment = Environment.current(environment).name
    self._mapper.clear()
    self._resolver.clear()
    self._bootstrapped.clear()
    return self

  def _describe_adapter(self, *, metadata: AdapterMetadata) -> str:
    flag = ' singleton' if metadata.lifecycle == LifecycleEnum.SINGLETON else ''
    return (
      f'  - {QualifiedName.of(metadata.adapter)} '
      f'key={metadata.key!r} envs={metadata.environment_label()}{flag}'
    )

  def _describe_binding(self, *, binding: PortBinding) -> list[str]:
    selected = QualifiedName.of(binding.selected.adapter) if binding.selected else '<none>'
    lines = ['', QualifiedName.of(binding.port), f'  selected: {selected}']
    lines.extend(self._describe_adapter(metadata=metadata) for metadata in binding.adapters)
    return lines

  def _has(self, port: type[Any], key: str | None = None) -> bool:
    """Whether an active adapter exists for ``port`` (drives ``@Invert`` optional deps)."""
    return self._mapper.find(port=port, key=key, environment=self._environment) is not None

  def _inject(self, port: type[Any], key: str | None = None) -> Any:
    """Resolve a port for ``@Invert`` (the only sanctioned construction trigger)."""
    return self._resolver.resolve(port=port, key=key, environment=self._environment)
