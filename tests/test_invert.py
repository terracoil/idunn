"""Tests for the @Invert constructor auto-injection decorator."""

from typing import Protocol

import pytest
from idunn.app import Adapter, Idunn, Invert, Port
from idunn.domain import AdapterNotFoundError, LifecycleEnum

from _support import Container


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


class OptionalConsumer:
  basket: BasketPort | None

  @Invert
  def __init__(self, basket: BasketPort | None = None) -> None:
    pass


class OptionalKeyedConsumer:
  basket: BasketPort | None

  @Invert(keys={'basket': 'missing'})
  def __init__(self, basket: BasketPort | None = None) -> None:
    pass


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
  Container.install(GoldenBasket)
  consumer = Consumer(label='hi')
  assert consumer.label == 'hi'
  assert isinstance(consumer.basket, GoldenBasket)
  assert consumer.basket.take() == 'golden'


def test_invert_caller_argument_overrides_injection() -> None:
  Container.install(GoldenBasket)

  class Manual:
    def take(self) -> str:
      return 'manual'

  manual = Manual()
  consumer = Consumer(basket=manual, label='hi')
  assert consumer.basket is manual


def test_invert_keys_selects_keyed_adapter() -> None:
  Container.install(PlainBasket)
  consumer = KeyedConsumer()
  assert isinstance(consumer.basket, PlainBasket)


def test_invert_keys_picks_keyed_while_plain_invert_picks_unkeyed() -> None:
  Container.install(GoldenBasket, PlainBasket)

  plain_consumer = Consumer(label='hi')
  keyed_consumer = KeyedConsumer()

  assert isinstance(plain_consumer.basket, GoldenBasket)
  assert isinstance(keyed_consumer.basket, PlainBasket)


def test_invert_explicit_map_injects_param() -> None:
  Container.install(GoldenBasket)
  consumer = ExplicitConsumer(label='x')
  assert consumer.label == 'x'
  assert isinstance(consumer.basket, GoldenBasket)


def test_invert_unregistered_port_raises() -> None:
  with pytest.raises(AdapterNotFoundError):
    Consumer(label='hi')


def test_invert_optional_dependency_honors_default_when_absent() -> None:
  # No adapter registered: the @Port-typed param has a default, so it stays the default.
  consumer = OptionalConsumer()
  assert consumer.basket is None


def test_invert_optional_dependency_injects_when_available() -> None:
  Container.install(GoldenBasket)
  consumer = OptionalConsumer()
  assert isinstance(consumer.basket, GoldenBasket)


def test_invert_optional_keyed_dependency_absent_uses_default() -> None:
  # An unkeyed adapter exists, but the requested key does not — optional, so default wins.
  Container.install(GoldenBasket)
  consumer = OptionalKeyedConsumer()
  assert consumer.basket is None


def test_invert_reset_clears_singleton_instance_cache() -> None:
  Container.install(GoldenBasket)
  first = Consumer(label='a').basket
  Idunn().reset(environment='local')
  Container.install(GoldenBasket)
  second = Consumer(label='b').basket
  assert isinstance(first, GoldenBasket)
  assert isinstance(second, GoldenBasket)
  assert first is not second  # reset dropped the cached singleton


def test_invert_resolves_nested_constructor_injection() -> None:
  Container.install(GoldenBasket, BasketService)
  consumer = ServiceConsumer()
  assert consumer.service.run() == 'service:golden'


def test_invert_shares_singleton_adapter_across_consumers() -> None:
  Container.install(GoldenBasket)
  first = Consumer(label='a')
  second = Consumer(label='b')
  assert first.basket is second.basket
