"""The port-to-adapter catalog: atomic batch registration and lock-free, env-filtered selection."""

from __future__ import annotations

from collections.abc import Iterable
from threading import Lock
from typing import Any, NoReturn

from idunn.domain import (
  AdapterDeclaration,
  AdapterMetadata,
  AdapterNotFoundError,
  Catalog,
  InvalidAdapterError,
  InvalidPortError,
  PortBinding,
  SlotKey,
)
from idunn.util import QualifiedName

from .inversion_validator import InversionValidator
from .port_registry import PortRegistry


class InversionMapper:
  """Owns the :class:`~idunn.domain.Catalog` and answers "which adapter for this port?".
  The catalog is copy-on-write. Readers take whichever snapshot is current and never lock. Writers
  queue on one lock, copy the catalog once, validate everything they add, and swap the result in
  with a single assignment, so a batch lands whole or not at all and nobody reads half of one.
  """

  def __init__(self) -> None:
    """Start with an empty catalog and an idle write lock."""
    self._catalog: Catalog = Catalog.empty()
    self._write_lock: Lock = Lock()

  def bindings(self, *, environment: str) -> tuple[PortBinding, ...]:
    """Return every port and its adapters in ``environment``, sorted by name.
    Reads one snapshot, so the adapter lists and the ``selected`` lines always agree, even while
    another thread registers.
    """
    catalog: Catalog = self._catalog
    grouped: dict[type[Any], list[AdapterMetadata]] = {port: [] for port in catalog.ports}
    for metadata in catalog.adapters.values():
      grouped[metadata.port].append(metadata)
    return tuple(
      PortBinding(
        port=port,
        selected=catalog.find(port=port, key=None, environment=environment),
        adapters=tuple(grouped[port]),
      )
      for port in sorted(catalog.ports, key=QualifiedName.of)
    )

  @property
  def catalog(self) -> Catalog:
    """The current snapshot. Keep it as long as you like: nothing will ever change it."""
    return self._catalog

  def clear(self) -> None:
    """Forget every port and adapter by swapping in an empty catalog."""
    with self._write_lock:
      self._catalog = Catalog.empty()

  def find(
    self,
    *,
    port: type[Any],
    key: str | None,
    environment: str,
  ) -> AdapterMetadata | None:
    """Return the active adapter for ``port`` and ``key`` in ``environment``, or ``None``.
    Hot path: one dict hit on the current snapshot and a filter over a slot of one or two.
    """
    return self._catalog.find(port=port, key=key, environment=environment)

  @property
  def ports(self) -> frozenset[type[Any]]:
    """Registered ports. Only the tests read this, to inspect the catalog without the facade."""
    return self._catalog.ports

  def register_adapter(self, adapter: type[Any]) -> bool:
    """Register one ``@Adapter`` class; return whether it was new. A batch of one."""
    return bool(self.register_batch(adapters=(adapter,))[1])

  def register_batch(
    self,
    *,
    ports: Iterable[type[Any]] = (),
    adapters: Iterable[type[Any]] = (),
  ) -> tuple[tuple[type[Any], ...], tuple[type[Any], ...]]:
    """Register ``ports``, then ``adapters``, all or nothing; return the ``(ports, adapters)`` new.
    Runs under the write lock against the latest catalog: copy once, fold, validate each new
    adapter against its slot (earlier registrations and this batch alike), then swap. An error
    propagates before the swap, leaving the catalog exactly as it was. A class already registered,
    or repeated in the batch, is skipped rather than refused, so two discoveries of one root can
    race harmlessly: whoever comes second simply finds nothing new.
    """
    with self._write_lock:
      current: Catalog = self._catalog
      known_ports: set[type[Any]] = set(current.ports)
      known_adapters: dict[type[Any], AdapterMetadata] = dict(current.adapters)
      slots: dict[SlotKey, tuple[AdapterMetadata, ...]] = dict(current.slots)
      new_ports: tuple[type[Any], ...] = self._fold_ports(ports=ports, known=known_ports)
      new_adapters: tuple[type[Any], ...] = self._fold_adapters(
        adapters=adapters, ports=known_ports, known=known_adapters, slots=slots
      )
      if new_ports or new_adapters:
        self._catalog = Catalog.freeze(ports=known_ports, adapters=known_adapters, slots=slots)
    return new_ports, new_adapters

  def register_port(self, port: type[Any]) -> bool:
    """Register a ``@Port`` Protocol; return whether it was new.
    Ports register on their own, not only through adapters, so ``describe()`` and the report
    still show a port that nobody has implemented yet.
    """
    return bool(self.register_batch(ports=(port,))[0])

  def restore(self, catalog: Catalog) -> None:
    """Swap back a catalog read earlier from :attr:`catalog`, undoing every batch since.
    No copy needed: a catalog never changes, so the old one is exactly as it was handed out.
    """
    with self._write_lock:
      self._catalog = catalog

  def select(self, *, port: type[Any], key: str | None, environment: str) -> AdapterMetadata:
    """Like :meth:`find`, but raise :class:`AdapterNotFoundError` when nothing matches."""
    found: AdapterMetadata | None = self.find(port=port, key=key, environment=environment)
    if found is None:
      self._raise_adapter_not_found(port=port, key=key, environment=environment)
    return found

  def _declaration_for(self, *, adapter: type[Any]) -> AdapterDeclaration:
    declaration: Any = getattr(adapter, '__idunn_adapter_declaration__', None)
    if declaration is None or not isinstance(declaration, AdapterDeclaration):
      message = f'Adapter class is not marked with @Adapter: {QualifiedName.of(adapter)}'
      raise InvalidAdapterError(message)
    return declaration

  def _fold_adapters(
    self,
    *,
    adapters: Iterable[type[Any]],
    ports: set[type[Any]],
    known: dict[type[Any], AdapterMetadata],
    slots: dict[SlotKey, tuple[AdapterMetadata, ...]],
  ) -> tuple[type[Any], ...]:
    # Mutates the batch's private working copies only; the live catalog is never touched here.
    new: list[type[Any]] = []
    for adapter in adapters:
      declaration: AdapterDeclaration = self._declaration_for(adapter=adapter)
      if adapter not in known:
        InversionValidator.validate_adapter_class(adapter=adapter, port=declaration.port)
        metadata: AdapterMetadata = AdapterMetadata(
          adapter=adapter,
          port=declaration.port,
          key=declaration.key,
          lifecycle=declaration.lifecycle,
          envs=declaration.envs,
        )
        slot: SlotKey = (metadata.port, metadata.key)
        InversionValidator.validate_registration(metadata=metadata, slot=slots.get(slot, ()))
        slots[slot] = (*slots.get(slot, ()), metadata)
        known[adapter] = metadata
        # Implicit, so not reported as new: the port is credited to whoever defines it.
        ports.add(metadata.port)
        new.append(adapter)
    return tuple(new)

  def _fold_ports(
    self, *, ports: Iterable[type[Any]], known: set[type[Any]]
  ) -> tuple[type[Any], ...]:
    new: list[type[Any]] = []
    for port in ports:
      if not PortRegistry.is_port(port):
        message = f'Port is not marked with @Port: {QualifiedName.of(port)}'
        raise InvalidPortError(message)
      if port not in known:
        known.add(port)
        new.append(port)
    return tuple(new)

  def _raise_adapter_not_found(
    self, *, port: type[Any], key: str | None, environment: str
  ) -> NoReturn:
    location = f'in {environment!r}'
    detail = f' with key {key!r}' if key is not None else ''
    message = f'No active adapter registered for port {QualifiedName.of(port)}{detail} {location}.'
    raise AdapterNotFoundError(message)
