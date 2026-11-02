"""``Idunn``: the process-wide facade, and the only door into the engine."""

from __future__ import annotations

from collections.abc import Iterable
from threading import RLock
from typing import Any

from idunn.domain import AdapterMetadata, LifecycleEnum, PortBinding, ReportMap
from idunn.internal import AutoDiscovery, InversionMapper, InversionResolver
from idunn.util import Environment, MetaSingleton, QualifiedName


class Idunn(metaclass=MetaSingleton):
  """Process-wide singleton facade: discover a graph, then let ``@Invert()`` wire it.
  ``Idunn()`` always returns the same instance, so there is nothing to pass around and nothing to
  lose. Application code rarely needs it: ``autodiscover()`` once at startup, or ``bootstrap()``
  from each library entry point, plus ``reset()`` and ``describe()`` for tests and the curious.
  Registration, selection and construction live behind it in
  :class:`~idunn.internal.InversionMapper` and :class:`~idunn.internal.InversionResolver`, and
  there is deliberately no public ``resolve()`` to tempt business code into calling it.
  """

  def __init__(self) -> None:
    """Bind to the environment from ``IDUNN_ENV`` (or ``local``) and start with an empty engine.
    Takes no arguments: this runs once per process, so an argument here would be honored once and
    then ignored forever. ``reset(environment=...)`` is the one place to choose.
    """
    self._environment: str = Environment.current().name
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
    Test modules (``tests``, ``test``, ``test_*``, ``*_test``, ``conftest``), any ``__main__`` and
    every ``exclude`` pattern are skipped; patterns match each dotted part below the root. The
    report lists only what this call newly registered, so running it twice is harmless and the
    second report is short.
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
    """Run ``autodiscover`` for ``root_package`` once, caching the report until ``reset()``.
    For libraries, which are imported rather than started and so have no startup hook: call it
    from every public entry point (a decorator, a classmethod, a ``__new__``) and the graph is
    wired on first use instead of at import. The first call for a root discovers with the options
    given; later calls return the cached :class:`~idunn.ReportMap` without rescanning and ignore
    their options. Distinct roots are cached independently, and a failed run is not cached at
    all. Thread-safe and re-entrant: a module imported mid-discovery may call ``bootstrap``
    itself without deadlocking anyone.
    """
    if root_package not in self._bootstrapped:
      with self._bootstrap_lock:
        if root_package not in self._bootstrapped:
          report = self.autodiscover(root_package, exclude=exclude, strict=strict)
          # A re-entered bootstrap (a module calling it mid-import) caches first and setdefault
          # keeps that report. It lists only what was registered before the re-entry, so a class
          # defined after the nested call is missing from the cached report; describe() has it.
          self._bootstrapped.setdefault(root_package, report)
    return self._bootstrapped[root_package]

  def describe(self) -> str:
    """Return a readable snapshot of the port-to-adapter bindings in the current environment.
    Its ``selected`` line is exactly what an unkeyed ``@Invert()`` parameter would receive.
    """
    lines = [f'Environment: {self._environment}']
    for binding in self._mapper.bindings(environment=self._environment):
      lines.extend(self._describe_binding(binding=binding))
    return '\n'.join(lines)

  @property
  def environment(self) -> str:
    """The environment adapters are filtered by, fixed at construction and on each ``reset()``."""
    return self._environment

  def reset(self, *, environment: str | None = None) -> Idunn:
    """Forget registrations, singletons and bootstrap memory, then rebind the environment.
    Returns ``self`` so tests can chain, e.g. ``Idunn().reset(environment='ci').environment``.
    """
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
    """Report whether ``port`` has an active adapter, so ``@Invert()`` can honor optional deps."""
    return self._mapper.find(port=port, key=key, environment=self._environment) is not None

  def _inject(self, port: type[Any], key: str | None = None) -> Any:
    """Resolve ``port`` for ``@Invert()``, the one sanctioned way to get something built."""
    return self._resolver.resolve(port=port, key=key, environment=self._environment)
