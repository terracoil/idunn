"""Registration guards: rejecting unmarked ports and malformed adapter declarations.
The realistic end-user path into these guards is the decorator (``@Port`` / ``@Adapter``
validate eagerly at decoration time). The validator's ``validate_adapter_class`` checks are
the mapper's defensive backstop for declarations that bypass the decorator, so the
malformed-declaration tests below hand-attach an ``AdapterDeclaration`` to drive the
backstop directly.
"""

from __future__ import annotations

import threading
from typing import Any, Protocol

import pytest

from idunn import InvalidAdapterError, InvalidPortError, LifecycleEnum, Port
from idunn.domain import AdapterDeclaration
from idunn.internal import InversionMapper


@Port
class SignalPort(Protocol):
  def emit(self) -> str: ...


class BareProtocol(Protocol):
  """A Protocol the user forgot to mark with @Port."""

  def emit(self) -> str: ...


def test_registering_an_unmarked_protocol_as_a_port_raises() -> None:
  mapper = InversionMapper()

  with pytest.raises(InvalidPortError, match=f'{__name__}.BareProtocol$'):
    mapper.register_batch(ports=(BareProtocol,))


def test_a_port_batch_reports_what_was_new_then_nothing() -> None:
  mapper = InversionMapper()

  assert mapper.register_batch(ports=(SignalPort,)) == ((SignalPort,), ())
  assert mapper.register_batch(ports=(SignalPort,)) == ((), ())
  assert mapper.catalog.ports == frozenset({SignalPort})


def test_a_declaration_on_a_non_class_raises() -> None:
  mapper = InversionMapper()

  def disguised_adapter() -> None: ...

  # Hand-attach a valid declaration to a non-class to reach the mapper's backstop.
  declaration = AdapterDeclaration(
    port=SignalPort, key=None, lifecycle=LifecycleEnum.TRANSIENT, envs=None
  )
  setattr(disguised_adapter, AdapterDeclaration.ATTRIBUTE, declaration)
  local = f'{__name__}.test_a_declaration_on_a_non_class_raises.<locals>'

  with pytest.raises(InvalidAdapterError) as refused:
    mapper.register_batch(adapters=(disguised_adapter,))  # type: ignore[arg-type]

  assert str(refused.value).endswith(f'{local}.disguised_adapter')


def test_a_declaration_naming_an_unmarked_port_raises() -> None:
  mapper = InversionMapper()

  class Sneaky:
    def emit(self) -> str:
      return 'sneaky'

  # A class declaration whose port skipped @Port: the backstop must reject it.
  AdapterDeclaration(
    port=BareProtocol, key=None, lifecycle=LifecycleEnum.TRANSIENT, envs=None
  ).attach(Sneaky)
  adapter: type[Any] = Sneaky

  with pytest.raises(InvalidPortError, match=f'{__name__}.BareProtocol$'):
    mapper.register_batch(adapters=(adapter,))


def test_a_stamp_that_is_not_a_declaration_is_no_adapter() -> None:
  mapper = InversionMapper()

  class Forged:
    def emit(self) -> str:
      return 'forged'

  setattr(Forged, AdapterDeclaration.ATTRIBUTE, 'trust me')

  with pytest.raises(InvalidAdapterError, match=r'not marked with @Adapter: .*\.Forged$'):
    mapper.register_batch(adapters=(Forged,))


def test_the_write_lock_is_deliberately_not_reentrant() -> None:
  # A batch re-entering registration would swap in a catalog built from a stale copy and lose the
  # inner update; a plain Lock deadlocks instead, which is the louder failure. Keep it that way.
  assert type(InversionMapper()._write_lock) is type(threading.Lock())
