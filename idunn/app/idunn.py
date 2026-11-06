"""``Idunn``: the process-wide facade, and the only door into the engine."""

from __future__ import annotations

from collections.abc import Iterable
from functools import partial
from typing import Any

from idunn.domain import (
  AdapterMetadata,
  EngineSnapshot,
  LifecycleEnum,
  ParameterPlan,
  PortBinding,
  ReportMap,
)
from idunn.internal import AutoDiscovery, BootstrapGate, InversionMapper, InversionResolver
from idunn.util import Environment, MetaSingleton, QualifiedName


class Idunn(metaclass=MetaSingleton):
  """Process-wide singleton facade: discover a graph, then let ``@Invert()`` wire it.
  ``Idunn()`` always returns the same instance, so there is nothing to pass around and nothing to
  lose. Application code rarely needs it: ``autodiscover()`` once at startup, or ``bootstrap()``
  from each library entry point, plus ``reset()`` and ``describe()`` for tests and the curious.
  Registration, selection and construction live behind it in
  :class:`~idunn.internal.InversionMapper` and :class:`~idunn.internal.InversionResolver`, and
  there is deliberately no public ``resolve()`` to tempt business code into calling it, nor a
  public register: tests that need one borrow ``idunn.testing.Harness``, which undoes itself.
  """

  def __init__(self) -> None:
    """Bind to the environment from ``IDUNN_ENV`` (or ``local``) and start with an empty engine.
    Takes no arguments: this runs once per process, so an argument here would be honored once and
    then ignored forever. ``reset(environment=...)`` is the one place to choose.
    """
    self._environment: str = Environment.current().name
    self._mapper: InversionMapper = InversionMapper()
    self._resolver: InversionResolver = InversionResolver(self._mapper)
    self._discovery: AutoDiscovery = AutoDiscovery(self._mapper)
    self._gate: BootstrapGate = BootstrapGate()

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
    return self._discovery.autodiscover(
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
    all. Thread-safe: concurrent first calls run one discovery and share its report, and a module
    may call ``bootstrap`` while it is being imported, in this thread or another, without
    deadlocking. Such a call cannot wait for anyone, so it discovers itself and returns its own
    run's report; the cached report merges every run of the root's first bootstrap, so nothing
    those runs registered goes missing from it.
    """
    cached: ReportMap | None = self._gate.cached(root_package)  # warm: no partial, no gate trip
    return (
      cached
      if cached is not None
      else self._gate.run(
        root_package,
        discover=partial(self.autodiscover, root_package, exclude=exclude, strict=strict),
      )
    )

  def describe(self) -> str:
    """Return a readable snapshot of the port-to-adapter bindings in the current environment.
    Its ``selected`` line is exactly what an unkeyed ``@Invert()`` parameter would receive.
    """
    lines: list[str] = [f'Environment: {self._environment}']
    for binding in self._mapper.bindings(environment=self._environment):
      lines.extend(self._describe_binding(binding=binding))
    return '\n'.join(lines)

  @property
  def environment(self) -> str:
    """The environment adapters are filtered by, fixed at construction and on each ``reset()``."""
    return self._environment

  def reset(self, *, environment: str | None = None) -> Idunn:
    """Forget registrations, singletons, adapter plans and bootstrap memory; rebind the environment.
    Returns ``self`` so tests can chain, e.g. ``Idunn().reset(environment='ci').environment``.
    """
    self._environment = Environment.current(environment).name
    self._mapper.clear()
    self._resolver.clear()
    self._gate.clear()
    return self

  def _describe_adapter(self, *, metadata: AdapterMetadata) -> str:
    flag: str = ' singleton' if metadata.lifecycle == LifecycleEnum.SINGLETON else ''
    return (
      f'  - {QualifiedName.of(metadata.adapter)} '
      f'key={metadata.key!r} envs={metadata.environment_label()}{flag}'
    )

  def _describe_binding(self, *, binding: PortBinding) -> list[str]:
    selected: str = QualifiedName.of(binding.selected.adapter) if binding.selected else '<none>'
    lines: list[str] = ['', QualifiedName.of(binding.port), f'  selected: {selected}']
    lines.extend(self._describe_adapter(metadata=metadata) for metadata in binding.adapters)
    return lines

  def _inject(self, parameter: ParameterPlan) -> Any:
    """Fill one ``@Invert`` parameter in the current environment: the single door into the engine.
    Tolerance (optional ports, defaults) is decided behind it, by the same rule adapter
    constructors use, so an ``@Invert`` function and an adapter cannot disagree about it.
    """
    return self._resolver.inject(parameter=parameter, environment=self._environment)

  def _install(self, adapters: tuple[type[Any], ...]) -> None:
    """Register ``adapters`` as one atomic batch, for ``Harness.install`` only."""
    self._mapper.register_batch(adapters=adapters)

  def _override(self, port: type[Any], instance: object, *, key: str | None) -> None:
    """Make ``port`` and ``key`` resolve to ``instance``, for ``Harness.override`` only."""
    self._resolver.override(port=port, key=key, instance=instance)

  def _restore(self, snapshot: EngineSnapshot) -> None:
    """Put the environment, catalog, singletons, overrides and bootstrap memory back as captured.
    Each part swaps in whole, the way ``reset()`` does, so a build or a discovery still running
    lands in what it started with and the restored state never hears about it.
    """
    self._environment = snapshot.environment
    self._mapper.restore(snapshot.catalog)
    self._resolver.restore(instances=snapshot.instances, overrides=snapshot.overrides)
    self._gate.restore(reports=snapshot.reports, carried=snapshot.carried)

  def _snapshot(self) -> EngineSnapshot:
    """Capture everything a ``Harness`` block may change, for :meth:`_restore` to put back."""
    instances, overrides = self._resolver.snapshot()
    reports, carried = self._gate.snapshot()
    return EngineSnapshot(
      environment=self._environment,
      catalog=self._mapper.catalog,
      instances=instances,
      overrides=overrides,
      reports=reports,
      carried=carried,
    )
