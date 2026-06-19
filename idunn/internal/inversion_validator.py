"""Stateless validation for Idunn adapter registration and resolution."""

from __future__ import annotations

import inspect
from typing import Any

from idunn.domain import AdapterMetadata, InvalidAdapterError, InvalidPortError


class InversionValidator:
  """Stateless checks for adapter classes, registrations, and resolved instances.

  Every method either returns ``None`` or raises an :class:`~idunn.domain.IdunnError`;
  it holds no state, so the mapper and resolver can call it freely.
  """

  @staticmethod
  def validate_adapter_class(*, adapter: type[Any], port: type[Any]) -> None:
    """Reject a non-class adapter or a port that is not marked with ``@Port``."""
    if not inspect.isclass(adapter):
      message = f'Adapter must be a class: {adapter!r}'
      raise InvalidAdapterError(message)
    if not getattr(port, '__idunn_port__', False):
      message = f'Adapter port is not marked with @Port: {port.__qualname__}'
      raise InvalidPortError(message)

  @classmethod
  def validate_registration(
    cls,
    *,
    metadata: AdapterMetadata,
    existing: tuple[AdapterMetadata, ...],
  ) -> None:
    """Reject a second adapter sharing a port+key that is active in an overlapping env."""
    for other in existing:
      shares_binding = (
        other.adapter is not metadata.adapter
        and other.port is metadata.port
        and other.key == metadata.key
      )
      if shares_binding and cls._environments_overlap(other.envs, metadata.envs):
        message = (
          f'Duplicate adapter key for {metadata.port.__qualname__} key={metadata.key!r} '
          f'in overlapping environments: {other.adapter.__qualname__} and '
          f'{metadata.adapter.__qualname__}.'
        )
        raise InvalidAdapterError(message)

  @staticmethod
  def validate_instance(*, port: type[Any], adapter: type[Any], instance: Any) -> None:
    """Reject an instance that does not structurally satisfy its port Protocol."""
    if not isinstance(instance, port):
      message = (
        f'Adapter {adapter.__qualname__} does not satisfy port {port.__qualname__}. '
        'Implement the Protocol structurally or inherit from the port explicitly.'
      )
      raise InvalidAdapterError(message)

  @staticmethod
  def _environments_overlap(
    left: frozenset[str] | None,
    right: frozenset[str] | None,
  ) -> bool:
    """Two adapters overlap when either is env-agnostic or they share an environment."""
    return left is None or right is None or bool(left.intersection(right))
