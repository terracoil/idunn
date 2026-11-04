"""The construction engine: recursive, plan-driven resolution with cycle detection."""

from __future__ import annotations

from collections.abc import Mapping
from threading import Lock
from types import MappingProxyType
from typing import Any, ClassVar

from idunn.domain import (
  AdapterMetadata,
  EngineSnapshot,
  InjectionCycleError,
  InvalidPortError,
  LifecycleEnum,
  ParameterPlan,
  SlotKey,
)
from idunn.util import KeyedLocks, QualifiedName

from .construction_stack import ConstructionStack
from .constructor_planner import ConstructorPlanner
from .inversion_mapper import InversionMapper
from .inversion_validator import InversionValidator
from .port_registry import PortRegistry

# One generation of singletons, swapped whole by clear(): the built instances, and one lock per
# adapter class guarding its first build. A resolve captures it once, at entry, and hands it down.
SingletonGeneration = tuple[dict[type[Any], Any], KeyedLocks[type[Any]]]


class InversionResolver:
  """Builds object graphs by filling each adapter's planned port parameters, recursively.
  Choosing the adapter is the mapper's job and deciding which parameters are ports is the
  :class:`ConstructorPlanner`'s; this class owns the recursion, the in-progress cycle stack, the
  cache of ``SINGLETON`` instances and the cache of constructor plans. ``@Invert`` wrappers and
  adapter constructors fill their parameters through the same :meth:`inject`, which is why an
  optional port behaves identically in both.
  A ``SINGLETON`` is built once per generation even when threads race for it: a cache miss walks
  the graph for cycles holding nothing, then builds under that adapter's own lock and checks the
  cache again inside it. The warm path never locks, and unrelated singletons never queue on each
  other, since a lock is only ever taken on the way down a dependency edge.
  Overrides (``idunn.testing``) answer a ``(port, key)`` ahead of selection, so a stand-in needs no
  adapter, no environment and no luck; outside a test there are none, and the hot path pays one
  identity test for the whole feature.
  """

  # Cache-miss sentinel: a cached singleton may be falsy, so None cannot double as 'not cached'.
  _MISSING: ClassVar[object] = object()
  # What snapshot() reports when nothing is overridden: a snapshot always holds a real mapping.
  _NO_OVERRIDES: ClassVar[Mapping[SlotKey, object]] = MappingProxyType({})

  def __init__(self, mapper: InversionMapper) -> None:
    """Bind the resolver to the catalog it asks for adapter selections."""
    self._mapper: InversionMapper = mapper
    self._generation: SingletonGeneration = ({}, KeyedLocks())
    # Per thread, the stack of the SINGLETON build now running, if any, for consumers built inside.
    self._building: ConstructionStack = ConstructionStack()
    # Per adapter class, filled on first build. No lock: a racing duplicate is an identical plan.
    self._plans: dict[type[Any], tuple[ParameterPlan, ...]] = {}
    # Copy-on-write like the catalog: replaced whole under the lock, read without it. None rather
    # than empty when there are none, because `is not None` is the cheapest test Python has and
    # every resolve pays it; an empty mapping's truth test cost twice as much.
    self._overrides: Mapping[SlotKey, object] | None = None
    self._override_lock: Lock = Lock()

  def clear(self) -> None:
    """Drop every cached singleton instance, constructor plan and override.
    Swaps in new containers instead of emptying the old ones, so a build still running lands its
    instance in the generation it started in, which nobody reads any more.
    """
    self._generation = ({}, KeyedLocks())
    self._plans = {}
    with self._override_lock:
      self._overrides = None

  def inject(self, *, parameter: ParameterPlan, environment: str) -> Any:
    """Fill ``parameter`` for ``environment``: its active adapter, or its fallback if tolerant.
    The one door for ``@Invert`` wrappers; adapter constructors use the same rule from inside.
    Starts from this thread's published construction stack, which is empty unless a ``SINGLETON``
    is being built further up: then the cycle walk and the stack check both see the consumer's
    edge, and a loop through it raises instead of recursing, or deadlocking two threads.
    """
    return self._inject(
      parameter=parameter,
      environment=environment,
      stack=self._building.current,
      generation=self._generation,
    )

  def override(self, *, port: type[Any], key: str | None, instance: object) -> None:
    """Answer ``port`` and ``key`` with ``instance`` from now on, ahead of any adapter.
    Checked here rather than at use, so a bad stand-in fails at the line that installed it: a
    class that is not a ``@Port`` raises :class:`InvalidPortError`, and an instance that does not
    satisfy the port raises :class:`InvalidAdapterError`, just as a built adapter would.
    """
    if not PortRegistry.is_port(port):
      message = f'Cannot override a class that is not marked with @Port: {QualifiedName.of(port)}'
      raise InvalidPortError(message)
    InversionValidator.validate_instance(port=port, adapter=type(instance), instance=instance)
    with self._override_lock:
      self._overrides = MappingProxyType({**(self._overrides or {}), (port, key): instance})

  def restore(self, snapshot: EngineSnapshot) -> None:
    """Put back the snapshot's overrides and a copy of its singletons, as a whole new generation.
    The copy and the fresh locks are the point: a build racing the restore finishes into the
    generation it captured, which nobody reads any more, exactly as with :meth:`clear`. Overrides
    go back first because a resolve captures its generation once but reads overrides as it goes:
    the other order lets one starting between the swaps build a singleton against the departing
    fake straight into the restored generation. Plans stay, since they depend only on the class.
    """
    with self._override_lock:
      self._overrides = snapshot.overrides or None
    self._generation = (dict(snapshot.instances), KeyedLocks())

  def snapshot(self) -> tuple[Mapping[type[Any], Any], Mapping[SlotKey, object]]:
    """Return a read-only copy of this generation's singletons, and the overrides as they stand.
    Overrides are immutable, so they are shared; the singletons are copied because the live dict
    keeps filling up after the picture is taken.
    """
    return MappingProxyType(dict(self._generation[0])), self._overrides or self._NO_OVERRIDES

  def _assert_acyclic(
    self,
    *,
    metadata: AdapterMetadata,
    environment: str,
    stack: tuple[type[Any], ...],
    instances: dict[type[Any], Any],
  ) -> None:
    # Dry-runs the build from `metadata` and raises InjectionCycleError if it would loop back,
    # constructing nothing and taking no lock. Without it, two threads racing the first build of a
    # cyclic singleton graph could each take one adapter's lock and wait for the other's forever.
    self._walk(
      adapter=metadata.adapter,
      path=(*stack, metadata.adapter),
      done=set(),
      environment=environment,
      instances=instances,
    )

  def _build(
    self,
    *,
    metadata: AdapterMetadata,
    port: type[Any],
    environment: str,
    stack: tuple[type[Any], ...],
    generation: SingletonGeneration,
  ) -> Any:
    adapter: type[Any] = metadata.adapter
    inner: tuple[type[Any], ...] = (*stack, adapter)
    instance: Any = adapter(
      **{
        parameter.name: self._inject(
          parameter=parameter, environment=environment, stack=inner, generation=generation
        )
        for parameter in self._plan_for(adapter)
      }
    )
    InversionValidator.validate_instance(port=port, adapter=adapter, instance=instance)
    return instance

  def _build_once(
    self,
    *,
    metadata: AdapterMetadata,
    port: type[Any],
    environment: str,
    stack: tuple[type[Any], ...],
    generation: SingletonGeneration,
  ) -> Any:
    # A SINGLETON missing from the cache a moment ago. Whoever gets the adapter's lock first builds
    # it; everyone queued behind finds it on the second look. The walk comes first, holding nothing.
    # The build publishes its stack, so a consumer made inside the constructor continues the path.
    # Singleton builds only: they are the ones holding a lock, and publishing around every
    # TRANSIENT build cost ~10% of a warm transient resolve. A consumer made inside a transient
    # constructor therefore starts its path at the innermost singleton, which still covers every
    # lock this thread holds.
    instances, locks = generation
    self._assert_acyclic(
      metadata=metadata, environment=environment, stack=stack, instances=instances
    )
    with locks.for_key(metadata.adapter):
      instance: Any = instances.get(metadata.adapter, self._MISSING)
      if instance is self._MISSING:
        with self._building.publishing((*stack, metadata.adapter)):
          instance = instances[metadata.adapter] = self._build(
            metadata=metadata,
            port=port,
            environment=environment,
            stack=stack,
            generation=generation,
          )
    return instance

  @staticmethod
  def _cycle(path: tuple[type[Any], ...]) -> InjectionCycleError:
    chain: str = ' -> '.join(QualifiedName.of(item) for item in path)
    return InjectionCycleError(f'Constructor injection cycle detected: {chain}')

  def _follow(
    self,
    *,
    parameter: ParameterPlan,
    path: tuple[type[Any], ...],
    done: set[type[Any]],
    environment: str,
    instances: dict[type[Any], Any],
  ) -> bool:
    # One edge of the walk, chosen exactly as _inject and _resolve would choose it. An override
    # and a tolerant parameter with nothing active have no edge: the build hands over the stand-in
    # or the fallback without building anything. A built singleton is a leaf, because the build
    # will not look inside it either.
    overridden: bool = self._overridden(parameter)
    found: AdapterMetadata | None = (
      None
      if overridden
      else self._mapper.find(port=parameter.port, key=parameter.key, environment=environment)
    )
    halted: bool = found is None and not (parameter.tolerant or overridden)
    if found is not None and found.adapter in path:
      raise self._cycle((*path, found.adapter))
    if found is not None and found.adapter not in instances and found.adapter not in done:
      halted = self._walk(
        adapter=found.adapter,
        path=(*path, found.adapter),
        done=done,
        environment=environment,
        instances=instances,
      )
    return halted

  def _inject(
    self,
    *,
    parameter: ParameterPlan,
    environment: str,
    stack: tuple[type[Any], ...],
    generation: SingletonGeneration,
  ) -> Any:
    # A `Port | None` parameter, or any port parameter with a default, survives a missing adapter,
    # unless an override stands in for it: then it gets the stand-in like anyone else.
    absent: bool = (
      parameter.tolerant
      and self._mapper.find(port=parameter.port, key=parameter.key, environment=environment) is None
      and not self._overridden(parameter)
    )
    return (
      parameter.fallback
      if absent
      else self._resolve(
        port=parameter.port,
        key=parameter.key,
        environment=environment,
        stack=stack,
        generation=generation,
      )
    )

  def _overridden(self, parameter: ParameterPlan) -> bool:
    overrides: Mapping[SlotKey, object] | None = self._overrides
    return overrides is not None and (parameter.port, parameter.key) in overrides

  def _plan_for(self, adapter: type[Any]) -> tuple[ParameterPlan, ...]:
    plan: tuple[ParameterPlan, ...] | None = self._plans.get(adapter)
    if plan is None:
      plan = ConstructorPlanner.plan_adapter(
        adapter, keyword_only=ConstructorPlanner.KEYWORD_ONLY_PORTS
      )
      self._plans[adapter] = plan  # only a plan that worked is kept; a failure retries next time
    return plan

  def _resolve(
    self,
    *,
    port: type[Any],
    key: str | None,
    environment: str,
    stack: tuple[type[Any], ...],
    generation: SingletonGeneration,
  ) -> Any:
    if not PortRegistry.is_port(port):
      message = f'Cannot resolve a class that is not marked with @Port: {QualifiedName.of(port)}'
      raise InvalidPortError(message)
    overrides: Mapping[SlotKey, object] | None = self._overrides  # None outside a Harness block
    if overrides is not None and (port, key) in overrides:
      instance: Any = overrides[(port, key)]
    else:
      metadata: AdapterMetadata = self._mapper.select(port=port, key=key, environment=environment)
      if metadata.adapter in stack:
        raise self._cycle((*stack, metadata.adapter))
      instance = generation[0].get(metadata.adapter, self._MISSING)  # the warm path: no lock
      if instance is self._MISSING and metadata.lifecycle == LifecycleEnum.SINGLETON:
        instance = self._build_once(
          metadata=metadata, port=port, environment=environment, stack=stack, generation=generation
        )
      elif instance is self._MISSING:
        instance = self._build(
          metadata=metadata, port=port, environment=environment, stack=stack, generation=generation
        )
    return instance

  def _walk(
    self,
    *,
    adapter: type[Any],
    path: tuple[type[Any], ...],
    done: set[type[Any]],
    environment: str,
    instances: dict[type[Any], Any],
  ) -> bool:
    # Depth-first, in plan order, like the build. Returns True once it meets a required port with
    # no adapter: the build raises AdapterNotFoundError there and never sees anything beyond, so
    # the walk stops too rather than report a cycle nobody would reach. `done` keeps diamonds
    # linear: a finished node has no way back onto the current path.
    halted: bool = any(
      self._follow(
        parameter=parameter, path=path, done=done, environment=environment, instances=instances
      )
      for parameter in self._plan_for(adapter)
    )
    done.add(adapter)
    return halted
