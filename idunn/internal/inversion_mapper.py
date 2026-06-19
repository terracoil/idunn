"""The port-to-adapter catalog: registration, environment-filtered selection, and caching."""

from __future__ import annotations

from typing import Any, NoReturn

from idunn.domain import (
  AdapterDeclaration,
  AdapterMetadata,
  AdapterNotFoundError,
  InvalidAdapterError,
  InvalidPortError,
  PortBinding,
  RegistrationKey,
)
from idunn.util import QualifiedName

from .inversion_validator import InversionValidator


class InversionMapper:
  """Owns the port/adapter registry and answers "which adapter for this port?".

  Selection is environment-filtered and memoized in a per-``(environment, key)`` cache
  that is invalidated whenever the registry mutates, so a hot resolve is a dict lookup
  rather than a filter-and-sort.
  """

  def __init__(self) -> None:
    """Start with an empty registry and a cold selection cache."""
    self._ports: set[type[Any]] = set()
    self._adapters: list[AdapterMetadata] = []
    self._registered_adapter_classes: set[type[Any]] = set()
    self._order: int = 0
    self._selection_cache: dict[tuple[str, RegistrationKey], AdapterMetadata | None] = {}
    self._dirty: bool = False

  @property
  def ports(self) -> frozenset[type[Any]]:
    """Registered ports."""
    return frozenset(self._ports)

  def clear(self) -> None:
    """Drop every port, adapter, and cached selection."""
    self._ports.clear()
    self._adapters.clear()
    self._registered_adapter_classes.clear()
    self._order = 0
    self._selection_cache.clear()
    self._dirty = False

  def register_port(self, port: type[Any]) -> bool:
    """Register a ``@Port`` Protocol; returns whether it was newly added."""
    if not getattr(port, '__idunn_port__', False):
      message = f'Port is not marked with @Port: {port.__qualname__}'
      raise InvalidPortError(message)
    is_new = port not in self._ports  # capture before add mutates membership
    self._ports.add(port)
    return is_new

  def register_adapter(self, adapter: type[Any]) -> bool:
    """Register a ``@Adapter``-marked class; returns whether it was newly added."""
    declaration = self._declaration_for(adapter=adapter)
    if adapter in self._registered_adapter_classes:
      return False  # already registered — idempotent no-op
    InversionValidator.validate_adapter_class(adapter=adapter, port=declaration.port)
    metadata = AdapterMetadata(
      adapter=adapter,
      port=declaration.port,
      key=declaration.key,
      lifecycle=declaration.lifecycle,
      envs=declaration.envs,
      order=self._order,
    )
    InversionValidator.validate_registration(metadata=metadata, existing=tuple(self._adapters))
    self._ports.add(metadata.port)
    self._adapters.append(metadata)
    self._registered_adapter_classes.add(adapter)
    self._order += 1
    self._dirty = True
    return True

  def find(
    self,
    *,
    port: type[Any],
    key: str | None,
    environment: str,
  ) -> AdapterMetadata | None:
    """Return the active adapter for a port+key in an environment, or ``None``.

    Hot path: after the first lookup per ``(environment, key)`` this is a dict hit;
    the cache is dropped wholesale whenever the registry mutates (see ``_refresh_cache``).
    """
    self._refresh_cache()
    cache_key = (environment, RegistrationKey(port=port, key=key))
    if cache_key not in self._selection_cache:
      candidates = self._active_candidates(port=port, key=key, environment=environment)
      self._selection_cache[cache_key] = candidates[0] if candidates else None
    return self._selection_cache[cache_key]

  def select(self, *, port: type[Any], key: str | None, environment: str) -> AdapterMetadata:
    """Like :meth:`find`, but raise :class:`AdapterNotFoundError` when nothing matches."""
    found = self.find(port=port, key=key, environment=environment)
    if found is None:
      self._raise_adapter_not_found(port=port, key=key, environment=environment)
    return found

  def bindings(self, *, environment: str) -> tuple[PortBinding, ...]:
    """Structured snapshot of every port and its adapters for the given environment."""
    snapshot: list[PortBinding] = []
    for port in sorted(self._ports, key=QualifiedName.of):
      adapters = tuple(metadata for metadata in self._adapters if metadata.port is port)
      selected = self.find(port=port, key=None, environment=environment)
      snapshot.append(PortBinding(port=port, selected=selected, adapters=adapters))
    return tuple(snapshot)

  def _refresh_cache(self) -> None:
    if self._dirty:
      self._selection_cache.clear()
      self._dirty = False

  def _active_candidates(
    self,
    *,
    port: type[Any],
    key: str | None,
    environment: str,
  ) -> list[AdapterMetadata]:
    return sorted(
      (
        metadata
        for metadata in self._adapters
        if metadata.port is port and metadata.is_available_in(environment) and metadata.key == key
      ),
      key=lambda item: item.order,
    )

  def _declaration_for(self, *, adapter: type[Any]) -> AdapterDeclaration:
    declaration = getattr(adapter, '__idunn_adapter_declaration__', None)
    if declaration is None or not isinstance(declaration, AdapterDeclaration):
      message = f'Adapter class is not marked with @Adapter: {adapter.__qualname__}'
      raise InvalidAdapterError(message)
    return declaration

  def _raise_adapter_not_found(
    self, *, port: type[Any], key: str | None, environment: str
  ) -> NoReturn:
    location = f'in {environment!r}'
    detail = f' with key {key!r}' if key is not None else ''
    message = f'No active adapter registered for port {port.__qualname__}{detail} {location}.'
    raise AdapterNotFoundError(message)
