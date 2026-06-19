"""The construction engine: recursive constructor-time resolution with cycle detection."""

from __future__ import annotations

import inspect
from typing import Any, ClassVar, get_type_hints

from idunn.domain import (
  AdapterMetadata,
  InjectionCycleError,
  InvalidPortError,
  LifecycleEnum,
  MissingTypeHintError,
)

from .decorator_support import DecoratorSupport
from .inversion_mapper import InversionMapper
from .inversion_validator import InversionValidator


class InversionResolver:
  """Builds object graphs by resolving each adapter's ``@Port``-typed constructor args.

  Selection is delegated to the :class:`InversionMapper`; this class owns the recursion,
  the in-progress cycle stack, and the cache of ``SINGLETON`` instances.
  """

  # Cache-miss sentinel: a resolved instance may legitimately be falsy, so we can't probe with None.
  _MISSING: ClassVar[object] = object()

  def __init__(self, mapper: InversionMapper) -> None:
    """Bind the resolver to the catalog it asks for adapter selections."""
    self._mapper: InversionMapper = mapper
    self._instances: dict[type[Any], Any] = {}

  def clear(self) -> None:
    """Drop every cached singleton instance."""
    self._instances.clear()

  def resolve(self, *, port: type[Any], key: str | None, environment: str) -> Any:
    """Resolve a port into an adapter instance for the active environment."""
    return self._resolve(port=port, key=key, environment=environment, stack=())

  def _resolve(
    self,
    *,
    port: type[Any],
    key: str | None,
    environment: str,
    stack: tuple[type[Any], ...],
  ) -> Any:
    if not getattr(port, '__idunn_port__', False):
      message = f'Cannot resolve a class that is not marked with @Port: {port.__qualname__}'
      raise InvalidPortError(message)
    metadata = self._mapper.select(port=port, key=key, environment=environment)
    if metadata.adapter in stack:
      cycle = ' -> '.join(item.__qualname__ for item in (*stack, metadata.adapter))
      raise InjectionCycleError(f'Constructor injection cycle detected: {cycle}')
    cached = self._instances.get(metadata.adapter, self._MISSING)
    return (
      cached
      if cached is not self._MISSING
      else self._build(metadata=metadata, port=port, environment=environment, stack=stack)
    )

  def _build(
    self,
    *,
    metadata: AdapterMetadata,
    port: type[Any],
    environment: str,
    stack: tuple[type[Any], ...],
  ) -> Any:
    instance = self._construct(
      adapter=metadata.adapter,
      environment=environment,
      stack=(*stack, metadata.adapter),
    )
    InversionValidator.validate_instance(port=port, adapter=metadata.adapter, instance=instance)
    if metadata.lifecycle == LifecycleEnum.SINGLETON:
      self._instances[metadata.adapter] = instance
    return instance

  def _construct(
    self,
    *,
    adapter: type[Any],
    environment: str,
    stack: tuple[type[Any], ...],
  ) -> Any:
    signature = inspect.signature(adapter.__init__)
    type_hints = get_type_hints(adapter.__init__)
    kwargs: dict[str, Any] = {}
    for parameter in list(signature.parameters.values())[1:]:
      self._populate_constructor_argument(
        adapter=adapter,
        parameter=parameter,
        type_hints=type_hints,
        kwargs=kwargs,
        environment=environment,
        stack=stack,
      )
    return adapter(**kwargs)

  def _populate_constructor_argument(
    self,
    *,
    adapter: type[Any],
    parameter: inspect.Parameter,
    type_hints: dict[str, Any],
    kwargs: dict[str, Any],
    environment: str,
    stack: tuple[type[Any], ...],
  ) -> None:
    if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
      return  # *args / **kwargs are never injected
    annotation = type_hints.get(parameter.name, parameter.annotation)
    port, optional = DecoratorSupport.port_from_annotation(annotation)
    if annotation is inspect.Signature.empty:
      self._handle_missing_annotation(adapter=adapter, parameter=parameter)
    elif port is not None:
      self._inject_port_argument(
        parameter=parameter,
        port=port,
        optional=optional,
        kwargs=kwargs,
        environment=environment,
        stack=stack,
      )
    elif parameter.default is inspect.Signature.empty:
      message = (
        f'Cannot constructor-inject {adapter.__qualname__}.{parameter.name}: '
        f'{annotation!r} is not an @Port and no default value was supplied.'
      )
      raise MissingTypeHintError(message)

  def _inject_port_argument(
    self,
    *,
    parameter: inspect.Parameter,
    port: type[Any],
    optional: bool,
    kwargs: dict[str, Any],
    environment: str,
    stack: tuple[type[Any], ...],
  ) -> None:
    # A `Port | None` param, or any @Port param with a default, tolerates a missing adapter.
    has_default = parameter.default is not inspect.Signature.empty
    absent = (optional or has_default) and self._mapper.find(
      port=port, key=None, environment=environment
    ) is None
    if absent and not has_default:
      kwargs[parameter.name] = None  # optional, no default → fall back to None
    elif not absent:
      kwargs[parameter.name] = self._resolve(
        port=port, key=None, environment=environment, stack=stack
      )
    # absent with a default: leave it out so the constructor's own default applies

  def _handle_missing_annotation(
    self,
    *,
    adapter: type[Any],
    parameter: inspect.Parameter,
  ) -> None:
    if parameter.default is inspect.Signature.empty:
      message = f'Missing constructor type hint for {adapter.__qualname__}.{parameter.name}'
      raise MissingTypeHintError(message)
