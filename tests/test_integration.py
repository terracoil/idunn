"""End-to-end: a user's package wired only through the public ``idunn`` surface.
``orchard_shop`` is written to disk once per module and discovered the way an application
would do it. Nothing here touches ``Idunn()`` internals or the engine seams: wiring happens
through ``autodiscover`` / ``bootstrap``, and every object graph starts at an ``@Invert()``
constructor, exactly as in user code.
"""

import importlib
from collections.abc import Iterator
from types import ModuleType

import pytest
from idunn import AdapterNotFoundError, Idunn, ReportMap

from _support import PackageWriter

# Lets `bin/devtool test unit` leave these out and `test integration` pick only these.
pytestmark = pytest.mark.integration


class Shop:
  """Source of the ``orchard_shop`` package and a loader for its modules."""

  NAME = 'orchard_shop'

  FILES: dict[str, str] = {
    # Ports live in a module called "contracts": the decorator counts, not the module name.
    'contracts.py': """
      from typing import Protocol
      from idunn import Port

      @Port
      class StockPort(Protocol):
        def count(self, sku: str) -> int: ...

      @Port
      class PricingPort(Protocol):
        currency: str
        def price(self, sku: str) -> int: ...

      @Port
      class AuditPort(Protocol):
        def record(self, line: str) -> None: ...
    """,
    # A structural singleton (no inheritance, lifecycle as a string) and a keyed sibling.
    'inventory/warehouse.py': """
      from idunn import Adapter
      from orchard_shop.contracts import StockPort

      @Adapter(StockPort, lifecycle='singleton', envs={'local', 'prod'})
      class WarehouseStock:
        def __init__(self) -> None:
          self.calls = 0

        def count(self, sku: str) -> int:
          self.calls += 1
          return 12

      @Adapter(StockPort, key='demo')
      class DemoStock(StockPort):
        def count(self, sku: str) -> int:
          return 1
    """,
    # Adapters in a private module, re-exported by the package; one of them depends on a port.
    'pricing/__init__.py': 'from ._engine import FixedPricing, LivePricing',
    'pricing/_engine.py': """
      from idunn import Adapter
      from orchard_shop.contracts import PricingPort, StockPort

      @Adapter(PricingPort, envs={'local', 'test'})
      class FixedPricing(PricingPort):
        currency = 'NOK'

        def price(self, sku: str) -> int:
          return 2

      @Adapter(PricingPort, envs='prod')
      class LivePricing:
        def __init__(self, stock: StockPort) -> None:
          self.stock = stock

        @property
        def currency(self) -> str:
          return 'EUR'

        def price(self, sku: str) -> int:
          return 100 // self.stock.count(sku)
    """,
    # A port that extends an undecorated Protocol, with its adapter in the same module.
    'greeting.py': """
      from typing import Protocol
      from idunn import Adapter, Port

      class GreeterPort(Protocol):
        def greet(self) -> str: ...

      @Port
      class LoudGreeterPort(GreeterPort, Protocol):
        def volume(self) -> int: ...

      @Adapter(LoudGreeterPort)
      class Shouter:
        def greet(self) -> str:
          return 'HELLO'

        def volume(self) -> int:
          return 11
    """,
    # The consumers: inferred ports, an optional port, a keyed pick, and an explicit mapping.
    'checkout.py': """
      from idunn import Invert
      from orchard_shop.contracts import AuditPort, PricingPort, StockPort
      from orchard_shop.greeting import LoudGreeterPort

      class Checkout:
        pricing: PricingPort
        stock: StockPort
        audit: AuditPort | None

        @Invert()
        def __init__(
          self, customer: str, pricing: PricingPort, stock: StockPort, audit: AuditPort | None = None
        ) -> None:
          self.customer = customer

        def total(self, sku: str, qty: int) -> int:
          amount = self.pricing.price(sku) * qty
          if self.audit is not None:
            self.audit.record(f'{self.customer} {sku} x{qty} = {amount} {self.pricing.currency}')
          return amount

      class DemoCheckout:
        stock: StockPort

        @Invert(keys={'stock': 'demo'})
        def __init__(self, stock: StockPort) -> None:
          pass

      class Kiosk:
        @Invert({'greeter': LoudGreeterPort})
        def __init__(self, greeter) -> None:
          pass
    """,
    # A library-style entry point that bootstraps its own root on first use.
    'api.py': """
      from idunn import Idunn
      from orchard_shop.checkout import Checkout

      class ShopApi:
        def __init__(self) -> None:
          Idunn().bootstrap('orchard_shop')
          self._checkout = Checkout(customer='api')

        def quote(self, sku: str) -> int:
          return self._checkout.total(sku, 1)
    """,
    # Import-safe entry module: discovery imports it, the guard keeps it inert.
    'main.py': """
      from idunn import Idunn
      from orchard_shop.checkout import Checkout

      if __name__ == '__main__':
        Idunn().autodiscover('orchard_shop')
        print(Checkout(customer='Bragi').total('apple', 3))
    """,
    # Excluded by default; discoverable on purpose as its own root.
    'tests/fakes.py': """
      from idunn import Adapter
      from orchard_shop.contracts import StockPort

      @Adapter(StockPort, envs='test')
      class FakeStock(StockPort):
        def count(self, sku: str) -> int:
          return 0
    """,
  }

  @classmethod
  def load(cls, module: str) -> ModuleType:
    """Import ``orchard_shop.<module>`` the way application code would."""
    return importlib.import_module(f'{cls.NAME}.{module}')


class Recorder:
  """A caller-supplied ``AuditPort`` implementation, never registered anywhere."""

  def __init__(self) -> None:
    self.lines: list[str] = []

  def record(self, line: str) -> None:
    self.lines.append(line)


@pytest.fixture(scope='module')
def shop(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
  patch = pytest.MonkeyPatch()
  PackageWriter(tmp_path=tmp_path_factory.mktemp('shop'), monkeypatch=patch).package(
    Shop.NAME, Shop.FILES
  )
  yield Shop.NAME
  patch.undo()


@pytest.fixture
def discovered(shop: str) -> ReportMap:
  return Idunn().autodiscover(shop)


def test_checkout_is_wired_from_modules_of_any_name(discovered: ReportMap) -> None:
  checkout = Shop.load('checkout').Checkout(customer='Bragi')

  assert checkout.total('apple', 3) == 6
  assert checkout.customer == 'Bragi'
  assert checkout.audit is None  # optional port with no adapter
  assert type(checkout.stock).__name__ == 'WarehouseStock'  # structural, never inherited the port
  assert set(discovered['registered_ports']) == {
    f'{Shop.NAME}.contracts.AuditPort',
    f'{Shop.NAME}.contracts.PricingPort',
    f'{Shop.NAME}.contracts.StockPort',
    f'{Shop.NAME}.greeting.LoudGreeterPort',
  }
  assert f'{Shop.NAME}.pricing._engine.FixedPricing' in discovered['registered_adapters']
  assert f'{Shop.NAME}.tests.fakes.FakeStock' not in discovered['registered_adapters']


def test_singleton_adapter_is_shared_and_transient_is_not(discovered: ReportMap) -> None:
  checkout_module = Shop.load('checkout')
  first = checkout_module.Checkout(customer='a')
  second = checkout_module.Checkout(customer='b')

  assert first.stock is second.stock
  assert first.pricing is not second.pricing


def test_keyed_adapter_is_picked_at_the_point_of_use(discovered: ReportMap) -> None:
  checkout_module = Shop.load('checkout')

  assert type(checkout_module.DemoCheckout().stock).__name__ == 'DemoStock'
  assert type(checkout_module.Checkout(customer='a').stock).__name__ == 'WarehouseStock'


def test_explicit_port_mapping_and_protocol_inheritance(discovered: ReportMap) -> None:
  kiosk = Shop.load('checkout').Kiosk()

  assert kiosk.greeter.greet() == 'HELLO'
  assert kiosk.greeter.volume() == 11


def test_caller_supplied_arguments_win_over_injection(discovered: ReportMap) -> None:
  recorder = Recorder()
  checkout = Shop.load('checkout').Checkout(customer='Idunn', audit=recorder)

  assert checkout.total('apple', 2) == 4
  assert checkout.audit is recorder
  assert recorder.lines == ['Idunn apple x2 = 4 NOK']


def test_prod_environment_selects_live_pricing_with_its_own_dependency(shop: str) -> None:
  Idunn().reset(environment='prod').autodiscover(shop)

  checkout = Shop.load('checkout').Checkout(customer='Bragi')

  assert type(checkout.pricing).__name__ == 'LivePricing'
  assert checkout.pricing.currency == 'EUR'
  assert checkout.pricing.stock is checkout.stock  # the adapter's dependency is the same singleton
  assert checkout.total('apple', 1) == 100 // 12


def test_test_environment_swaps_in_fakes_from_their_own_root(shop: str) -> None:
  Idunn().reset(environment='test').autodiscover(shop)
  checkout_module = Shop.load('checkout')

  # The warehouse is not active in 'test', and the fakes package is excluded by default.
  with pytest.raises(AdapterNotFoundError):
    checkout_module.Checkout(customer='a')

  Idunn().autodiscover(f'{shop}.tests')

  assert type(checkout_module.Checkout(customer='a').stock).__name__ == 'FakeStock'


def test_library_bootstraps_itself_on_first_use(shop: str) -> None:
  api_module = Shop.load('api')

  assert api_module.ShopApi().quote('apple') == 2
  assert api_module.ShopApi().quote('apple') == 2
  assert Idunn().bootstrap(shop) is Idunn().bootstrap(shop)


def test_describe_shows_the_selected_adapter_per_port(discovered: ReportMap) -> None:
  rendered = Idunn().describe()

  assert 'Environment: local' in rendered
  assert f'{Shop.NAME}.contracts.StockPort' in rendered
  assert f'selected: {Shop.NAME}.inventory.warehouse.WarehouseStock' in rendered
  assert f'selected: {Shop.NAME}.pricing._engine.FixedPricing' in rendered
