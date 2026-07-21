"""Registration guards: rejecting unmarked ports and malformed adapter declarations.

The realistic end-user path into these guards is the decorator (``@Port`` / ``@Adapter``
validate eagerly at decoration time). The validator's ``validate_adapter_class`` checks are
the mapper's defensive backstop for declarations that bypass the decorator, so the
malformed-declaration tests below hand-attach an ``AdapterDeclaration`` to drive the
backstop directly.
"""

from __future__ import annotations

from typing import Any, Protocol

import pytest
from idunn import InvalidAdapterError, InvalidPortError, LifecycleEnum
from idunn.app import Port
from idunn.domain import AdapterDeclaration
from idunn.internal import InversionMapper


@Port
class SignalPort(Protocol):
  def emit(self) -> str: ...


class BareProtocol(Protocol):
  """A Protocol the user forgot to mark with @Port."""

  def emit(self) -> str: ...


def test_register_port_rejects_unmarked_protocol() -> None:
  mapper = InversionMapper()

  with pytest.raises(InvalidPortError):
    mapper.register_port(BareProtocol)


def test_register_port_reports_newly_added_then_idempotent() -> None:
  mapper = InversionMapper()

  assert mapper.register_port(SignalPort) is True
  assert mapper.register_port(SignalPort) is False
  assert mapper.ports == frozenset({SignalPort})


def test_register_adapter_with_non_class_declaration_raises() -> None:
  mapper = InversionMapper()

  def disguised_adapter() -> None: ...

  # Hand-attach a valid declaration to a non-class to reach the mapper's backstop.
  disguised_adapter.__idunn_adapter_declaration__ = AdapterDeclaration(  # type: ignore[attr-defined]
    port=SignalPort, key=None, lifecycle=LifecycleEnum.TRANSIENT, envs=None
  )

  with pytest.raises(InvalidAdapterError):
    mapper.register_adapter(disguised_adapter)  # type: ignore[arg-type]


def test_register_adapter_with_unmarked_port_declaration_raises() -> None:
  mapper = InversionMapper()

  class Sneaky:
    def emit(self) -> str:
      return 'sneaky'

  # A class declaration whose port skipped @Port — the backstop must reject it.
  Sneaky.__idunn_adapter_declaration__ = AdapterDeclaration(  # type: ignore[attr-defined]
    port=BareProtocol, key=None, lifecycle=LifecycleEnum.TRANSIENT, envs=None
  )
  adapter: type[Any] = Sneaky

  with pytest.raises(InvalidPortError):
    mapper.register_adapter(adapter)
