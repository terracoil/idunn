"""Every way to hold a decorator wrong, and the error each one earns.
Messages name the culprit as ``module.QualName``. A bare ``__qualname__`` sends you hunting through
every module that has a ``Feast``; ``Port(5)`` used to answer with an ``AttributeError`` about the
message itself, which helped nobody.
"""

from __future__ import annotations

import re
from typing import Protocol, TypeVar

import pytest
from idunn import Adapter, InvalidAdapterError, InvalidPortError, Invert, Port
from idunn.domain import AdapterDeclaration
from idunn.internal import PortRegistry

T_co = TypeVar('T_co', covariant=True)


@Port
class BasketPort(Protocol):
  def take(self) -> str: ...


class UnmarkedProtocol(Protocol):
  """A Protocol nobody remembered to mark with ``@Port``."""

  def take(self) -> str: ...


class GenericPort(Protocol[T_co]):
  """A generic Protocol; only the class itself may be a port, never ``GenericPort[int]``."""

  def take(self) -> T_co: ...


class PlainClass:
  """Not a Protocol, not anything really."""


def make_basket() -> BasketPort:
  """Build nothing; a function is not a class, however much it would like to be."""
  raise NotImplementedError


def test_port_on_a_non_class_raises_invalid_port_error() -> None:
  with pytest.raises(InvalidPortError, match=r'Protocol classes: 5$'):
    Port(5)  # type: ignore[type-var]


def test_port_on_a_plain_class_names_it_in_full() -> None:
  with pytest.raises(InvalidPortError, match=re.escape(f'{__name__}.PlainClass')):
    Port(PlainClass)


def test_port_on_a_parameterized_protocol_raises_invalid_port_error() -> None:
  # The alias forwards _is_protocol, so only the class check stops it before PortRegistry.mark.
  with pytest.raises(InvalidPortError, match=re.escape(f'{__name__}.GenericPort[int]')):
    Port(GenericPort[int])

  assert not PortRegistry.is_port(GenericPort[int])


def test_adapter_for_a_non_class_port_raises_invalid_port_error() -> None:
  with pytest.raises(InvalidPortError, match=r'not marked with @Port: 5$'):
    Adapter(5)  # type: ignore[arg-type]


def test_adapter_for_an_unmarked_protocol_names_it_in_full() -> None:
  with pytest.raises(InvalidPortError, match=re.escape(f'{__name__}.UnmarkedProtocol')):
    Adapter(UnmarkedProtocol)


def test_adapter_on_a_function_raises_invalid_adapter_error() -> None:
  with pytest.raises(InvalidAdapterError, match=re.escape(f'{__name__}.make_basket')):
    Adapter(BasketPort)(make_basket)  # type: ignore[type-var]


def test_stacked_adapter_raises_and_keeps_the_first_declaration() -> None:
  @Adapter(BasketPort)
  class GoldenBasket(BasketPort):
    def take(self) -> str:
      return 'golden'

  expected = f'{__name__}.test_stacked_adapter_raises_and_keeps_the_first_declaration'

  with pytest.raises(InvalidAdapterError, match=re.escape(f'{expected}.<locals>.GoldenBasket')):
    Adapter(BasketPort, key='outer')(GoldenBasket)

  # Refused before any stamp, so the original declaration is exactly as it was.
  declaration: AdapterDeclaration = vars(GoldenBasket)['__idunn_adapter_declaration__']
  assert declaration.key is None


def test_stacked_adapter_written_as_two_decorators_raises() -> None:
  with pytest.raises(InvalidAdapterError, match='more than once'):

    @Adapter(BasketPort, key='outer')
    @Adapter(BasketPort)
    class TwiceBadged(BasketPort):
      def take(self) -> str:
        return 'twice'


def test_redecorated_subclass_wears_its_own_badge() -> None:
  @Adapter(BasketPort)
  class GoldenBasket(BasketPort):
    def take(self) -> str:
      return 'golden'

  @Adapter(BasketPort, key='green')
  class GreenBasket(GoldenBasket):
    def take(self) -> str:
      return 'green'

  parent: AdapterDeclaration = vars(GoldenBasket)['__idunn_adapter_declaration__']
  child: AdapterDeclaration = vars(GreenBasket)['__idunn_adapter_declaration__']
  assert (parent.key, child.key) == (None, 'green')


def test_bare_invert_raises_type_error_naming_the_constructor() -> None:
  expected = f'{__name__}.test_bare_invert_raises_type_error_naming_the_constructor'

  with pytest.raises(TypeError, match=re.escape(f'{expected}.<locals>.Feast.__init__')):

    class Feast:
      @Invert  # type: ignore[arg-type, misc]
      def __init__(self, *, basket: BasketPort) -> None:
        self.basket = basket
