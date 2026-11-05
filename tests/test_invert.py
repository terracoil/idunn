"""``@Invert()`` from the consumer's side: inference, keys, explicit maps, optional ports."""

from enum import Enum, StrEnum
from typing import Protocol

import pytest

from idunn import Adapter, AdapterNotFoundError, Idunn, Invert, LifecycleEnum, Port
from idunn.domain import AdapterDeclaration
from idunn.testing import Harness


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

  @Invert()
  def __init__(self, label: str, *, basket: BasketPort) -> None:
    self.label = label


class KeyedConsumer:
  basket: BasketPort

  @Invert(keys={'basket': 'plain'})
  def __init__(self, *, basket: BasketPort) -> None:
    pass


class ExplicitConsumer:
  basket: object

  @Invert({'basket': BasketPort})
  def __init__(self, label: str, *, basket: object) -> None:
    self.label = label


class OptionalConsumer:
  basket: BasketPort | None

  @Invert()
  def __init__(self, *, basket: BasketPort | None = None) -> None:
    pass


class OptionalKeyedConsumer:
  basket: BasketPort | None

  @Invert(keys={'basket': 'missing'})
  def __init__(self, *, basket: BasketPort | None = None) -> None:
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

  @Invert()
  def __init__(self, *, service: ServicePort) -> None:
    pass


def test_invert_auto_injects_and_assigns_self() -> None:
  with Harness.install(GoldenBasket):
    consumer = Consumer(label='hi')
    assert consumer.label == 'hi'
    assert isinstance(consumer.basket, GoldenBasket)
    assert consumer.basket.take() == 'golden'


def test_the_constructor_body_can_already_use_self_port() -> None:
  class Feast:
    basket: BasketPort

    @Invert()
    def __init__(self, *, basket: BasketPort) -> None:
      self.first: str = self.basket.take()  # assigned before the body runs, as promised

  with Harness.install(GoldenBasket):
    assert Feast().first == 'golden'


def test_invert_caller_argument_overrides_injection() -> None:
  class Manual:
    def take(self) -> str:
      return 'manual'

  manual = Manual()
  with Harness.install(GoldenBasket):
    consumer = Consumer(basket=manual, label='hi')
  assert consumer.basket is manual


def test_invert_keys_selects_keyed_adapter() -> None:
  with Harness.install(PlainBasket):
    consumer = KeyedConsumer()
    assert isinstance(consumer.basket, PlainBasket)


def test_invert_keys_picks_keyed_while_plain_invert_picks_unkeyed() -> None:
  with Harness.install(GoldenBasket, PlainBasket):
    plain_consumer = Consumer(label='hi')
    keyed_consumer = KeyedConsumer()

    assert isinstance(plain_consumer.basket, GoldenBasket)
    assert isinstance(keyed_consumer.basket, PlainBasket)


def test_a_str_enum_key_reaches_the_adapter_from_either_spelling() -> None:
  class Grade(StrEnum):
    GOLD = 'gold'

  @Adapter(BasketPort, key=Grade.GOLD)
  class GradedBasket(BasketPort):
    def take(self) -> str:
      return 'graded'

  class ByEnum:
    basket: BasketPort

    @Invert(keys={'basket': Grade.GOLD})
    def __init__(self, *, basket: BasketPort) -> None:
      pass

  class ByString:
    basket: BasketPort

    @Invert(keys={'basket': 'gold'})
    def __init__(self, *, basket: BasketPort) -> None:
      pass

  # A StrEnum member is a str that hashes and compares as its value, so one slot answers both.
  with Harness.install(GradedBasket):
    assert ByEnum().basket.take() == ByString().basket.take() == 'graded'


def test_an_enum_key_is_kept_as_its_plain_value_everywhere_it_is_stored_or_printed() -> None:
  class Grade(StrEnum):
    GOLD = 'gold'
    SILVER = 'silver'

  class Mixin(str, Enum):  # str() of this member says 'Mixin.GOLD', which must not be the key
    GOLD = 'gold'

  class Spare:
    def take(self) -> str:
      return 'spare'

  @Adapter(BasketPort, key=Grade.GOLD)
  class GradedBasket(BasketPort):
    def take(self) -> str:
      return 'graded'

  class Wanting:
    basket: BasketPort

    @Invert(keys={'basket': Grade.SILVER})
    def __init__(self, *, basket: BasketPort) -> None:
      pass

  @Invert(keys={'basket': Mixin.GOLD})
  def by_mixin(*, basket: BasketPort) -> str:
    return basket.take()

  @Invert(keys={'basket': 'silver'})
  def by_string(*, basket: BasketPort) -> str:
    return basket.take()

  declaration: AdapterDeclaration | None = AdapterDeclaration.of(GradedBasket)
  assert declaration is not None and type(declaration.key) is str
  with Harness.install(GradedBasket):
    assert "key='gold'" in Idunn().describe() and '<Grade' not in Idunn().describe()
    assert by_mixin() == 'graded'
    with pytest.raises(AdapterNotFoundError, match="with key 'silver' in 'local'"):
      Wanting()
    with Harness.override(BasketPort, Spare(), key=Grade.SILVER):
      assert by_string() == Wanting().basket.take() == 'spare'


def test_invert_explicit_map_injects_param() -> None:
  with Harness.install(GoldenBasket):
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


def test_a_port_with_a_non_none_default_gets_that_default_when_absent() -> None:
  class SpareBasket:
    def take(self) -> str:
      return 'spare'

  spare = SpareBasket()

  class Feast:
    basket: BasketPort

    @Invert()
    def __init__(self, *, basket: BasketPort = spare) -> None:
      pass

  assert Feast().basket is spare
  with Harness.install(GoldenBasket):
    assert isinstance(Feast().basket, GoldenBasket)


def test_a_union_of_two_ports_is_no_port_at_all() -> None:
  # `Port | None` is the optional spelling; with two ports in the union, which would it be?
  @Port
  class LedgerPort(Protocol):
    def note(self) -> str: ...

  class Feast:
    @Invert()
    def __init__(self, *, basket: BasketPort | LedgerPort | None = None) -> None:
      self.received: object = basket

  with Harness.install(GoldenBasket):
    assert Feast().received is None


def test_invert_optional_dependency_injects_when_available() -> None:
  with Harness.install(GoldenBasket):
    consumer = OptionalConsumer()
    assert isinstance(consumer.basket, GoldenBasket)


def test_invert_optional_keyed_dependency_absent_uses_default() -> None:
  # An unkeyed adapter exists, but the requested key does not — optional, so default wins.
  with Harness.install(GoldenBasket):
    consumer = OptionalKeyedConsumer()
    assert consumer.basket is None


def test_invert_install_block_takes_its_singletons_with_it() -> None:
  with Harness.install(GoldenBasket):
    first = Consumer(label='a').basket
  with Harness.install(GoldenBasket):
    second = Consumer(label='b').basket
  assert isinstance(first, GoldenBasket)
  assert isinstance(second, GoldenBasket)
  assert first is not second  # the first block's exit dropped the cached singleton


def test_invert_resolves_nested_constructor_injection() -> None:
  with Harness.install(GoldenBasket, BasketService):
    consumer = ServiceConsumer()
    assert consumer.service.run() == 'service:golden'


def test_invert_shares_singleton_adapter_across_consumers() -> None:
  with Harness.install(GoldenBasket):
    first = Consumer(label='a')
    second = Consumer(label='b')
    assert first.basket is second.basket
