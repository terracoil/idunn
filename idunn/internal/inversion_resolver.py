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
from idunn.util import QualifiedName

from .constructor_planner import ConstructorPlanner
from .inversion_mapper import InversionMapper
from .inversion_validator import InversionValidator
from .port_registry import PortRegistry


class InversionResolver:
  """Builds object graphs by filling each adapter's planned port parameters, recursively.
  Choosing the adapter is the mapper's job and deciding which parameters are ports is the
  :class:`ConstructorPlanner`'s; this class owns the recursion, the in-progress cycle stack, the
  cache of ``SINGLETON`` instances and the cache of constructor plans. ``@Invert`` wrappers and
  adapter constructors fill their parameters through the same :meth:`inject`, which is why an
  optional port behaves identically in both.
  """

  # Cache-miss sentinel: a cached singleton may be falsy, so None cannot double as 'not cached'.
  _MISSING: ClassVar[object] = object()

  def __init__(self, mapper: InversionMapper) -> None:
    """Bind the resolver to the catalog it asks for adapter selections."""
    self._mapper: InversionMapper = mapper
    self._instances: dict[type[Any], Any] = {}
    # Per adapter class, filled on first build. No lock: a racing duplicate is an identical plan.
    self._plans: dict[type[Any], tuple[ParameterPlan, ...]] = {}

  def clear(self) -> None:
    """Drop every cached singleton instance and constructor plan."""
    self._instances.clear()
    self._plans = {}

  def inject(self, *, parameter: ParameterPlan, environment: str) -> Any:
    """Fill ``parameter`` for ``environment``: its active adapter, or its fallback if tolerant.
    The one door for ``@Invert`` wrappers; adapter constructors use the same rule from inside.
    """
    return self._inject(parameter=parameter, environment=environment, stack=())

  def _build(
    self,
    *,
    metadata: AdapterMetadata,
    port: type[Any],
    environment: str,
    stack: tuple[type[Any], ...],
  ) -> Any:
    adapter: type[Any] = metadata.adapter
    inner: tuple[type[Any], ...] = (*stack, adapter)
    instance: Any = adapter(
      **{
        parameter.name: self._inject(parameter=parameter, environment=environment, stack=inner)
        for parameter in self._plan_for(adapter)
      }
    )
    InversionValidator.validate_instance(port=port, adapter=adapter, instance=instance)
    if metadata.lifecycle == LifecycleEnum.SINGLETON:
      self._instances[adapter] = instance
    return instance

  def _inject(
    self,
    *,
    parameter: ParameterPlan,
    environment: str,
    stack: tuple[type[Any], ...],
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
        port=parameter.port, key=parameter.key, environment=environment, stack=stack
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
  ) -> Any:
    if not PortRegistry.is_port(port):
      message = f'Cannot resolve a class that is not marked with @Port: {QualifiedName.of(port)}'
      raise InvalidPortError(message)
    metadata = self._mapper.select(port=port, key=key, environment=environment)
    if metadata.adapter in stack:
      cycle = ' -> '.join(QualifiedName.of(item) for item in (*stack, metadata.adapter))
      raise InjectionCycleError(f'Constructor injection cycle detected: {cycle}')
    cached = self._instances.get(metadata.adapter, self._MISSING)
    return (
      cached
      if cached is not self._MISSING
      else self._build(metadata=metadata, port=port, environment=environment, stack=stack)
    )
