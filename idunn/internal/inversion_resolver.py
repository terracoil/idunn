"""The construction engine: recursive, plan-driven resolution with cycle detection."""

from __future__ import annotations

from typing import Any, ClassVar

from idunn.domain import (
  AdapterMetadata,
  InjectionCycleError,
  InvalidPortError,
  LifecycleEnum,
  ParameterPlan,
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
  """

  # Cache-miss sentinel: a cached singleton may be falsy, so None cannot double as 'not cached'.
  _MISSING: ClassVar[object] = object()

  def __init__(self, mapper: InversionMapper) -> None:
    """Bind the resolver to the catalog it asks for adapter selections."""
    self._mapper: InversionMapper = mapper
    self._generation: SingletonGeneration = ({}, KeyedLocks())
    # Per thread, the stack of the SINGLETON build now running, if any, for consumers built inside.
    self._building: ConstructionStack = ConstructionStack()
    # Per adapter class, filled on first build. No lock: a racing duplicate is an identical plan.
    self._plans: dict[type[Any], tuple[ParameterPlan, ...]] = {}

  def clear(self) -> None:
    """Drop every cached singleton instance and constructor plan.
    Swaps in new containers instead of emptying the old ones, so a build still running lands its
    instance in the generation it started in, which nobody reads any more.
    """
    self._generation = ({}, KeyedLocks())
    self._plans = {}

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
    # One edge of the walk, chosen exactly as _inject and _resolve would choose it. A tolerant
    # parameter with nothing active gets its fallback, so there is no edge; a built singleton is
    # a leaf, because the build will not look inside it either.
    found: AdapterMetadata | None = self._mapper.find(
      port=parameter.port, key=parameter.key, environment=environment
    )
    halted: bool = found is None and not parameter.tolerant
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
    # A `Port | None` parameter, or any port parameter with a default, survives a missing adapter.
    absent: bool = (
      parameter.tolerant
      and self._mapper.find(port=parameter.port, key=parameter.key, environment=environment) is None
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
    metadata: AdapterMetadata = self._mapper.select(port=port, key=key, environment=environment)
    if metadata.adapter in stack:
      raise self._cycle((*stack, metadata.adapter))
    instance: Any = generation[0].get(metadata.adapter, self._MISSING)  # the warm path: no lock
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
