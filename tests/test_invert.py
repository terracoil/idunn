"""Tests for the @Invert constructor auto-injection decorator."""

from typing import Protocol

import pytest
from idunn import Adapter, AdapterNotFoundError, Idunn, Invert, LifecycleEnum, Port


@Port
class BasketPort(Protocol):
  def take(self) -> str: ...


@Adapter(BasketPort, lifecycle=LifecycleEnum.SINGLETON)
class GoldenBasket(BasketPort):
  def take(self) -> str:
    return 'golden'


@Adapter(BasketPort, key='plain')
class PlainBasket(BasketPort):
  def take(self) -> str:
    return 'plain'


class Consumer:
  basket: BasketPort  # declared for the type checker; assigned by @Invert at runtime

  @Invert
  def __init__(self, basket: BasketPort, label: str) -> None:
    self.label = label


class KeyedConsumer:
  basket: BasketPort

  @Invert(keys={'basket': 'plain'})
  def __init__(self, basket: BasketPort) -> None:
    pass


class ExplicitConsumer:
  basket: object

  @Invert({'basket': BasketPort})
  def __init__(self, basket: object, label: str) -> None:
    self.label = label


@Port
class ServicePort(Protocol):
  def run(self) -> str: ...


@Adapter(ServicePort)
class BasketService(ServicePort):
  def __init__(self, basket: BasketPort) -> None:
    self._basket = basket

  def run(self) -> str:
    return f'service:{self._basket.take()}'


class ServiceConsumer:
  service: ServicePort

  @Invert
  def __init__(self, service: ServicePort) -> None:
    pass


def test_invert_auto_injects_and_assigns_self() -> None:
  Idunn().register_adapter(GoldenBasket)
  consumer = Consumer(label='hi')
  assert consumer.label == 'hi'
  assert isinstance(consumer.basket, GoldenBasket)
  assert consumer.basket.take() == 'golden'


def test_invert_caller_argument_overrides_injection() -> None:
  Idunn().register_adapter(GoldenBasket)

  class Manual:
    def take(self) -> str:
      return 'manual'

  manual = Manual()
  consumer = Consumer(basket=manual, label='hi')
  assert consumer.basket is manual


def test_invert_keys_selects_keyed_adapter() -> None:
  Idunn().register_adapter(PlainBasket)
  consumer = KeyedConsumer()
  assert isinstance(consumer.basket, PlainBasket)


def test_invert_explicit_map_injects_param() -> None:
  Idunn().register_adapter(GoldenBasket)
  consumer = ExplicitConsumer(label='x')
  assert consumer.label == 'x'
  assert isinstance(consumer.basket, GoldenBasket)


def test_invert_unregistered_port_raises() -> None:
  with pytest.raises(AdapterNotFoundError):
    Consumer(label='hi')


def test_invert_resolves_nested_constructor_injection() -> None:
  Idunn().register_adapter(GoldenBasket)
  Idunn().register_adapter(BasketService)
  consumer = ServiceConsumer()
  assert consumer.service.run() == 'service:golden'


def test_invert_shares_singleton_adapter_across_consumers() -> None:
  Idunn().register_adapter(GoldenBasket)
  first = Consumer(label='a')
  second = Consumer(label='b')
  assert first.basket is second.basket
