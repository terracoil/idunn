"""Idunn: the process-wide singleton engine for constructor-time injection."""

from __future__ import annotations

import inspect
from collections.abc import Iterable, Mapping
from typing import Any, get_type_hints

from idunn.domain import (
  AdapterDeclaration,
  AdapterMetadata,
  AdapterNotFoundError,
  InjectionCycleError,
  InvalidAdapterError,
  InvalidPortError,
  LifecycleEnum,
  MissingTypeHintError,
  RegistrationKey,
  ReportMap,
)
from idunn.internal import AutoDiscovery
from idunn.util import Environment, MetaSingleton


class Idunn(metaclass=MetaSingleton):
  """Process-wide singleton: stores port→adapter mappings and resolves object graphs."""

  def __init__(self, *, environment: str | None = None) -> None:
    """Create an empty table bound to the given (or resolved) environment."""
    self._environment = Environment.current(environment).name
    self._ports: set[type[Any]] = set()
    self._adapters: list[AdapterMetadata] = []
    self._instances: dict[type[Any], Any] = {}
    self._registered_adapter_classes: set[type[Any]] = set()
    self._order = 0

  @property
  def environment(self) -> str:
    """Active environment used for adapter filtering."""
    return self._environment

  @property
  def ports(self) -> frozenset[type[Any]]:
    """Registered ports."""
    return frozenset(self._ports)

  @property
  def adapters(self) -> Mapping[RegistrationKey, tuple[AdapterMetadata, ...]]:
    """Registered adapter metadata grouped by port and optional key."""
    grouped: dict[RegistrationKey, list[AdapterMetadata]] = {}
    for metadata in self._adapters:
      key = RegistrationKey(port=metadata.port, key=metadata.key)
      grouped.setdefault(key, []).append(metadata)
    return {key: tuple(values) for key, values in grouped.items()}

  def clear(self) -> None:
    """Clear ports, adapters, and singleton instances."""
    self._ports.clear()
    self._adapters.clear()
    self._instances.clear()
    self._registered_adapter_classes.clear()
    self._order = 0

  def autodiscover(
    self,
    root_package: str,
    *,
    port_package_names: Iterable[str] | None = None,
    adapter_package_names: Iterable[str] | None = None,
    strict: bool = True,
  ) -> ReportMap:
    """Discover decorated ports first, then decorated adapters."""
    return AutoDiscovery().autodiscover(
      table=self,
      root_package=root_package,
      port_package_names=frozenset(port_package_names) if port_package_names is not None else None,
      adapter_package_names=(
        frozenset(adapter_package_names) if adapter_package_names is not None else None
      ),
      strict=strict,
    )

  def reset(self, *, environment: str | None = None) -> Idunn:
    """Clear all state and rebind the environment; returns the singleton."""
    self.clear()
    self._environment = Environment.current(environment).name
    return self

  def register_port(self, port: type[Any]) -> bool:
    """Register a port Protocol."""
    if not getattr(port, '__idunn_port__', False):
      message = f'Port is not marked with @Port: {port.__qualname__}'
      raise InvalidPortError(message)
    is_new = port not in self._ports  # capture before add mutates membership
    self._ports.add(port)
    return is_new

  def register_adapter(self, adapter: type[Any]) -> bool:
    """Register a class previously marked with @Adapter."""
    declaration = self._declaration_for(adapter=adapter)
    return self._register_declared_adapter(adapter=adapter, declaration=declaration)

  def resolve(self, port: type[Any], *, key: str | None = None) -> Any:
    """Resolve a port into an adapter instance."""
    return self._resolve(port, key=key, stack=())

  def construct(self, adapter: type[Any]) -> Any:
    """Construct an adapter class by resolving its port-annotated constructor args."""
    return self._construct(adapter=adapter, stack=())

  def describe(self) -> str:
    """Return a readable description of the table."""
    lines = [f'Environment: {self._environment}']
    for port in sorted(self._ports, key=self._qualified_name):
      lines.extend(self._describe_port(port=port))
    return '\n'.join(lines)

  def _register_declared_adapter(
    self,
    *,
    adapter: type[Any],
    declaration: AdapterDeclaration,
  ) -> bool:
    if adapter in self._registered_adapter_classes:
      return False  # already registered — idempotent no-op
    self._validate_adapter_class(adapter=adapter, declaration=declaration)
    metadata = AdapterMetadata(
      adapter=adapter,
      port=declaration.port,
      key=declaration.key,
      lifecycle=declaration.lifecycle,
      default=declaration.default,
      envs=declaration.envs,
      order=self._order,
    )
    self._validate_registration(metadata=metadata)
    self._ports.add(metadata.port)  # Add (idempotently) to set
    self._adapters.append(metadata)  # Append to list
    self._registered_adapter_classes.add(adapter)  # Add (idempotently) to set
    self._order += 1
    return True

  def _declaration_for(self, *, adapter: type[Any]) -> AdapterDeclaration:
    declaration = getattr(adapter, '__idunn_adapter_declaration__', None)
    if declaration is None or not isinstance(declaration, AdapterDeclaration):
      message = f'Adapter class is not marked with @Adapter: {adapter.__qualname__}'
      raise InvalidAdapterError(message)
    return declaration

  def _validate_adapter_class(
    self,
    *,
    adapter: type[Any],
    declaration: AdapterDeclaration,
  ) -> None:
    if not inspect.isclass(adapter):
      message = f'Adapter must be a class: {adapter!r}'
      raise InvalidAdapterError(message)
    if not getattr(declaration.port, '__idunn_port__', False):
      message = f'Adapter port is not marked with @Port: {declaration.port.__qualname__}'
      raise InvalidPortError(message)

  def _validate_registration(self, *, metadata: AdapterMetadata) -> None:
    for existing in self._adapters:
      if existing.adapter is metadata.adapter:
        continue
      if existing.port is metadata.port and existing.key == metadata.key:
        self._validate_key_overlap(existing=existing, metadata=metadata)
      if existing.port is metadata.port and existing.default and metadata.default:
        self._validate_default_overlap(existing=existing, metadata=metadata)

  def _validate_key_overlap(
    self,
    *,
    existing: AdapterMetadata,
    metadata: AdapterMetadata,
  ) -> None:
    if self._environments_overlap(existing.envs, metadata.envs):
      message = (
        f'Duplicate adapter key for {metadata.port.__qualname__} key={metadata.key!r} '
        f'in overlapping environments: {existing.adapter.__qualname__} and '
        f'{metadata.adapter.__qualname__}.'
      )
      raise InvalidAdapterError(message)

  def _validate_default_overlap(
    self,
    *,
    existing: AdapterMetadata,
    metadata: AdapterMetadata,
  ) -> None:
    if self._environments_overlap(existing.envs, metadata.envs):
      message = (
        f'Multiple default adapters for {metadata.port.__qualname__} in overlapping '
        f'environments: {existing.adapter.__qualname__} and '
        f'{metadata.adapter.__qualname__}.'
      )
      raise InvalidAdapterError(message)

  def _environments_overlap(
    self,
    left: frozenset[str] | None,
    right: frozenset[str] | None,
  ) -> bool:
    return left is None or right is None or bool(left.intersection(right))

  def _resolve(
    self,
    port: type[Any],
    *,
    key: str | None,
    stack: tuple[type[Any], ...],
  ) -> Any:
    if not getattr(port, '__idunn_port__', False):
      message = f'Cannot resolve a class that is not marked with @Port: {port.__qualname__}'
      raise InvalidPortError(message)

    metadata = self._select_adapter(port=port, key=key)
    if metadata.adapter in stack:
      cycle = ' -> '.join(item.__qualname__ for item in (*stack, metadata.adapter))
      raise InjectionCycleError(f'Constructor injection cycle detected: {cycle}')

    if metadata.lifecycle == LifecycleEnum.SINGLETON and metadata.adapter in self._instances:
      return self._instances[metadata.adapter]
    instance = self._construct(adapter=metadata.adapter, stack=(*stack, metadata.adapter))
    self._validate_instance(port=port, adapter=metadata.adapter, instance=instance)
    if metadata.lifecycle == LifecycleEnum.SINGLETON:
      self._instances[metadata.adapter] = instance
    return instance

  def _construct(self, adapter: type[Any], stack: tuple[type[Any], ...]) -> Any:
    signature = inspect.signature(adapter.__init__)
    type_hints = get_type_hints(adapter.__init__)
    kwargs: dict[str, Any] = {}

    for parameter in list(signature.parameters.values())[1:]:
      self._populate_constructor_argument(
        adapter=adapter,
        parameter=parameter,
        type_hints=type_hints,
        kwargs=kwargs,
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
    stack: tuple[type[Any], ...],
  ) -> None:
    if parameter.kind not in (
      inspect.Parameter.VAR_POSITIONAL,
      inspect.Parameter.VAR_KEYWORD,
    ):
      annotation = type_hints.get(parameter.name, parameter.annotation)
      if annotation is inspect.Signature.empty:
        self._handle_missing_annotation(adapter=adapter, parameter=parameter)
      elif getattr(annotation, '__idunn_port__', False):
        kwargs[parameter.name] = self._resolve(annotation, key=None, stack=stack)
      elif parameter.default is inspect.Signature.empty:
        message = (
          f'Cannot constructor-inject {adapter.__qualname__}.{parameter.name}: '
          f'{annotation!r} is not an @Port and no default value was supplied.'
        )
        raise MissingTypeHintError(message)

  def _handle_missing_annotation(
    self,
    *,
    adapter: type[Any],
    parameter: inspect.Parameter,
  ) -> None:
    if parameter.default is inspect.Signature.empty:
      message = f'Missing constructor type hint for {adapter.__qualname__}.{parameter.name}'
      raise MissingTypeHintError(message)

  def _select_adapter(self, *, port: type[Any], key: str | None) -> AdapterMetadata:
    candidates = self._active_candidates(port=port, key=key)
    if not candidates:
      self._raise_adapter_not_found(port=port, key=key)
    return (
      candidates[0]
      if key is not None
      else self._select_default_or_first(port=port, candidates=candidates)
    )

  def _active_candidates(self, *, port: type[Any], key: str | None) -> list[AdapterMetadata]:
    candidates: list[AdapterMetadata] = [
      metadata
      for metadata in self._adapters
      if metadata.port is port
      and metadata.is_available_in(self._environment)
      and (key is None or metadata.key == key)
    ]
    candidates.sort(key=lambda item: item.order)
    return candidates

  def _select_default_or_first(
    self,
    *,
    port: type[Any],
    candidates: list[AdapterMetadata],
  ) -> AdapterMetadata:
    defaults = [metadata for metadata in candidates if metadata.default]
    if len(defaults) > 1:
      adapter_names = ', '.join(self._qualified_name(item.adapter) for item in defaults)
      message = f'Multiple active default adapters for {port.__qualname__}: {adapter_names}'
      raise InvalidAdapterError(message)
    return defaults[0] if defaults else candidates[0]

  def _raise_adapter_not_found(self, *, port: type[Any], key: str | None) -> None:
    if key is None:
      message = (
        f'No active adapter registered for port {port.__qualname__} in {self._environment!r}.'
      )
    else:
      message = (
        f'No active adapter registered for port {port.__qualname__} with key {key!r} '
        f'in {self._environment!r}.'
      )
    raise AdapterNotFoundError(message)

  def _validate_instance(self, *, port: type[Any], adapter: type[Any], instance: Any) -> None:
    if not isinstance(instance, port):
      message = (
        f'Adapter {adapter.__qualname__} does not satisfy port {port.__qualname__}. '
        'Implement the Protocol structurally or inherit from the port explicitly.'
      )
      raise InvalidAdapterError(message)

  def _describe_port(self, *, port: type[Any]) -> list[str]:
    lines = ['', f'{self._qualified_name(port)}']
    active = self._active_candidates(port=port, key=None)
    if active:
      selected = self._select_default_or_first(port=port, candidates=active)
      lines.append(f'  default: {self._qualified_name(selected.adapter)}')
    else:
      lines.append('  default: <none>')
    for metadata in self._adapters:
      if metadata.port is port:
        lines.append(self._describe_adapter(metadata=metadata))
    return lines

  def _describe_adapter(self, *, metadata: AdapterMetadata) -> str:
    flags: list[str] = []
    if metadata.default:
      flags.append('default')
    if metadata.lifecycle == LifecycleEnum.SINGLETON:
      flags.append('singleton')
    flag_text = f' {" ".join(flags)}' if flags else ''
    return (
      f'  - {self._qualified_name(metadata.adapter)} '
      f'key={metadata.key!r} envs={metadata.environment_label()}{flag_text}'
    )

  def _qualified_name(self, obj: type[Any]) -> str:
    return f'{obj.__module__}.{obj.__qualname__}'
