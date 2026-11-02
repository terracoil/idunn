"""``@Invert()`` on plain functions and methods: ports arrive as keyword arguments, nothing is kept.
Anything not named ``__init__`` is a function to Idunn. Its port parameters are filled at call time
by the same rules as a constructor's (caller wins, optional ports, keys, explicit maps, deferred
hints), and the wrapper assigns nothing anywhere: no ``self.<name>``, no attribute on the function.
"""

import functools
from collections.abc import Callable
from typing import Any, Protocol, cast

import pytest
from idunn import (
  Adapter,
  AdapterNotFoundError,
  Idunn,
  InvalidPortError,
  Invert,
  LifecycleEnum,
  Port,
)
from idunn.domain import InvertDeclaration

from _support import Container


@Port
class BasketPort(Protocol):
  def take(self) -> str: ...


@Port
class LedgerPort(Protocol):
  def note(self, line: str) -> str: ...


@Port
class ServicePort(Protocol):
  def run(self) -> str: ...


@Adapter(BasketPort, lifecycle=LifecycleEnum.SINGLETON)
class GoldenBasket(BasketPort):
  def take(self) -> str:
    return 'golden'


@Adapter(BasketPort, key='plain')
class PlainBasket(BasketPort):
  def take(self) -> str:
    return 'plain'


@Adapter(LedgerPort)
class InkLedger(LedgerPort):
  def note(self, line: str) -> str:
    return f'noted {line}'


@Adapter(ServicePort)
class BasketService(ServicePort):
  def __init__(self, basket: BasketPort) -> None:
    self._basket = basket

  def run(self) -> str:
    return f'service:{self._basket.take()}'


class Manual:
  def take(self) -> str:
    return 'manual'


@Invert()
def pick(*, basket: BasketPort) -> str:
  return basket.take()


@Invert()
def pick_first(label: str = '', *, basket: BasketPort) -> str:
  return f'{label}{basket.take()}'


@Invert(keys={'basket': 'plain'})
def pick_plain(order: str, *, basket: BasketPort, ledger: LedgerPort | None = None) -> str:
  return ledger.note(f'{order} {basket.take()}') if ledger is not None else basket.take()


@Invert({'basket': BasketPort})
def describe(label: str, *, basket: object) -> str:
  return f'{label}:{cast(BasketPort, basket).take()}'  # mapped, so it is a basket


@Invert()
def serve(*, service: ServicePort) -> str:
  return service.run()


@Invert()
def basket_service(*, basket: BasketPort) -> BasketService:
  """Build an adapter by hand: Idunn supplies the port, the helper calls the constructor."""
  return BasketService(basket)


class Till:
  @Invert()
  def ring(self, amount: int, *, basket: BasketPort) -> str:
    return f'{basket.take()} x{amount}'

  @staticmethod
  @Invert()
  def peek(*, basket: BasketPort) -> str:
    return basket.take()


def test_a_function_receives_its_ports_as_keyword_arguments() -> None:
  Container.install(GoldenBasket)

  assert pick() == 'golden'


def test_a_function_assigns_nothing_anywhere() -> None:
  Container.install(GoldenBasket)
  till = Till()

  assert till.ring(3) == 'golden x3'
  assert 'basket' not in vars(till)
  assert 'basket' not in vars(pick)
  assert 'basket' not in vars(Till.ring)


def test_a_caller_supplied_argument_wins_and_ports_go_by_keyword_only() -> None:
  # Nothing is registered: had injection been attempted, it would have raised.
  assert pick(basket=Manual()) == 'manual'
  assert pick_first('by hand: ', basket=Manual()) == 'by hand: manual'
  with pytest.raises(TypeError, match='takes 1 positional argument but 2 were given'):
    pick_first('by hand: ', Manual())
  with pytest.raises(TypeError, match='takes 2 positional arguments but 3 were given'):
    Till().ring(2, Manual())  # the instance counts, as Python counts it
  with pytest.raises(TypeError, match='takes 0 positional arguments but 1 was given'):
    Till.peek(Manual())


def test_a_function_keeps_its_name_its_return_value_and_its_declaration() -> None:
  Container.install(GoldenBasket)

  assert pick.__name__ == 'pick'
  assert pick.__wrapped__ is not None  # type: ignore[attr-defined]
  assert InvertDeclaration.of(pick) is not None
  assert isinstance(basket_service(), BasketService)


def test_keys_and_an_optional_port_apply_to_functions() -> None:
  Container.install(GoldenBasket, PlainBasket)

  assert pick_plain('a') == 'plain'  # the ledger is optional and absent
  Container.install(InkLedger)
  assert pick_plain('a') == 'noted a plain'


def test_an_explicit_map_applies_to_functions() -> None:
  Container.install(GoldenBasket)

  assert describe('fruit') == 'fruit:golden'


def test_a_missing_required_port_raises_adapter_not_found() -> None:
  with pytest.raises(AdapterNotFoundError):
    pick()


def test_resolution_behind_a_function_is_recursive() -> None:
  Container.install(GoldenBasket, BasketService)

  assert serve() == 'service:golden'


def test_a_function_can_build_an_adapter_by_hand_from_injected_ports() -> None:
  Container.install(GoldenBasket)

  assert basket_service().run() == 'service:golden'


def test_methods_and_static_methods_are_functions_too() -> None:
  Container.install(GoldenBasket)

  assert Till().ring(2) == 'golden x2'
  assert Till.peek() == 'golden'


def test_functions_follow_the_current_environment() -> None:
  Container.install(GoldenBasket)
  first = pick()

  Idunn().reset(environment='prod')

  assert first == 'golden'
  with pytest.raises(AdapterNotFoundError):
    pick()


def test_a_stacked_invert_on_a_function_raises() -> None:
  with pytest.raises(TypeError, match='more than once'):
    Invert()(pick)


def test_a_function_with_an_unknown_name_in_its_map_raises_at_decoration() -> None:
  def take(*, basket: BasketPort) -> str:
    return basket.take()

  with pytest.raises(TypeError, match="names 'bucket'"):
    Invert({'bucket': BasketPort})(take)


def test_a_mapped_function_parameter_must_be_keyword_only() -> None:
  def take(basket: object) -> str:
    return str(basket)

  with pytest.raises(TypeError, match="maps or keys 'basket', which must be keyword-only"):
    Invert({'basket': BasketPort})(take)


def test_a_map_on_a_port_annotated_function_parameter_raises() -> None:
  def take(*, basket: BasketPort) -> str:
    return basket.take()

  with pytest.raises(InvalidPortError, match='already annotated with'):
    Invert({'basket': BasketPort})(take)


def test_a_key_on_a_non_port_function_parameter_raises() -> None:
  def take(*, label: str) -> str:
    return label

  with pytest.raises(InvalidPortError, match="keys 'label'"):
    Invert(keys={'label': 'plain'})(take)


def test_a_function_wrapped_by_another_decorator_still_counts_as_inverted() -> None:
  def logged(function: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
      return function(*args, **kwargs)

    return wrapper

  Container.install(GoldenBasket)
  logged_pick = logged(pick)

  assert logged_pick() == 'golden'
  with pytest.raises(TypeError, match='more than once'):
    Invert()(logged_pick)
