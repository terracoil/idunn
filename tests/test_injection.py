from typing import Protocol

import pytest
from idunn import (
  Adapter,
  AdapterNotFoundError,
  InjectionCycleError,
  InvalidAdapterError,
  InvalidPortError,
  LifecycleEnum,
  MissingTypeHintError,
  Port,
)

from _support import Wiring


def test_constructor_time_injection() -> None:
  table = Wiring()

  @Port
  class AppleBasketPort(Protocol):
    def take_apple(self) -> str: ...

  @Adapter(AppleBasketPort)
  class GoldenAppleBasketAdapter(AppleBasketPort):
    def take_apple(self) -> str:
      return 'golden apple'

  @Port
  class FeastPort(Protocol):
    def serve(self) -> str: ...

  @Adapter(FeastPort)
  class FeastAdapter(FeastPort):
    def __init__(self, basket: AppleBasketPort) -> None:
      self._basket = basket

    def serve(self) -> str:
      return self._basket.take_apple()

  table.register_adapter(GoldenAppleBasketAdapter)
  table.register_adapter(FeastAdapter)

  feast = table.resolve(FeastPort)

  assert feast.serve() == 'golden apple'


def test_singleton_lifecycle_reuses_instance() -> None:
  table = Wiring()

  @Port
  class CounterPort(Protocol):
    pass

  @Adapter(CounterPort, lifecycle=LifecycleEnum.SINGLETON)
  class CounterAdapter(CounterPort):
    pass

  table.register_adapter(CounterAdapter)

  first = table.resolve(CounterPort)
  second = table.resolve(CounterPort)

  assert first is second


def test_unkeyed_resolve_returns_unkeyed_adapter() -> None:
  table = Wiring()

  @Port
  class AppleBasketPort(Protocol):
    def take_apple(self) -> str: ...

  @Adapter(AppleBasketPort)
  class GoldenAppleBasketAdapter(AppleBasketPort):
    def take_apple(self) -> str:
      return 'golden apple'

  table.register_adapter(GoldenAppleBasketAdapter)

  assert isinstance(table.resolve(AppleBasketPort), GoldenAppleBasketAdapter)

  @Adapter(AppleBasketPort, key='orchard')
  class OrchardAppleBasketAdapter(AppleBasketPort):
    def take_apple(self) -> str:
      return 'orchard apple'

  table.register_adapter(OrchardAppleBasketAdapter)

  # The keyed adapter is opt-in; an unkeyed resolve still returns the unkeyed one.
  assert isinstance(table.resolve(AppleBasketPort), GoldenAppleBasketAdapter)
  assert isinstance(table.resolve(AppleBasketPort, key='orchard'), OrchardAppleBasketAdapter)


def test_unkeyed_resolve_ignores_keyed_adapters() -> None:
  table = Wiring()

  @Port
  class AppleBasketPort(Protocol):
    def take_apple(self) -> str: ...

  # Register the keyed adapter FIRST to prove registration order does not leak it in.
  @Adapter(AppleBasketPort, key='orchard')
  class OrchardAppleBasketAdapter(AppleBasketPort):
    def take_apple(self) -> str:
      return 'orchard apple'

  @Adapter(AppleBasketPort)
  class GoldenAppleBasketAdapter(AppleBasketPort):
    def take_apple(self) -> str:
      return 'golden apple'

  table.register_adapter(OrchardAppleBasketAdapter)
  table.register_adapter(GoldenAppleBasketAdapter)

  assert isinstance(table.resolve(AppleBasketPort), GoldenAppleBasketAdapter)


def test_unkeyed_resolve_with_only_keyed_adapters_raises() -> None:
  table = Wiring()

  @Port
  class AppleBasketPort(Protocol):
    def take_apple(self) -> str: ...

  @Adapter(AppleBasketPort, key='orchard')
  class OrchardAppleBasketAdapter(AppleBasketPort):
    def take_apple(self) -> str:
      return 'orchard apple'

  table.register_adapter(OrchardAppleBasketAdapter)

  with pytest.raises(AdapterNotFoundError):
    table.resolve(AppleBasketPort)
  assert isinstance(table.resolve(AppleBasketPort, key='orchard'), OrchardAppleBasketAdapter)


def test_environment_specific_selection(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setenv('IDUNN_ENV', 'test')
  table = Wiring()

  @Port
  class PaymentPort(Protocol):
    def charge(self) -> str: ...

  @Adapter(PaymentPort, envs={'prod'})
  class StripePaymentAdapter(PaymentPort):
    def charge(self) -> str:
      return 'stripe'

  @Adapter(PaymentPort, envs={'test', 'ci'})
  class FakePaymentAdapter(PaymentPort):
    def charge(self) -> str:
      return 'fake'

  table.register_adapter(StripePaymentAdapter)
  table.register_adapter(FakePaymentAdapter)

  assert isinstance(table.resolve(PaymentPort), FakePaymentAdapter)


def test_environment_can_be_passed_to_table() -> None:
  table = Wiring(environment='prod')

  @Port
  class PaymentPort(Protocol):
    def charge(self) -> str: ...

  @Adapter(PaymentPort, envs={'prod'})
  class StripePaymentAdapter(PaymentPort):
    def charge(self) -> str:
      return 'stripe'

  @Adapter(PaymentPort, envs={'test'})
  class FakePaymentAdapter(PaymentPort):
    def charge(self) -> str:
      return 'fake'

  table.register_adapter(StripePaymentAdapter)
  table.register_adapter(FakePaymentAdapter)

  assert isinstance(table.resolve(PaymentPort), StripePaymentAdapter)


def test_adapter_without_envs_is_available_everywhere() -> None:
  table = Wiring(environment='prod')

  @Port
  class ClockPort(Protocol):
    pass

  @Adapter(ClockPort)
  class SystemClockAdapter(ClockPort):
    pass

  table.register_adapter(SystemClockAdapter)

  assert isinstance(table.resolve(ClockPort), SystemClockAdapter)


def test_same_key_is_allowed_for_disjoint_environments() -> None:
  table = Wiring(environment='prod')

  @Port
  class PaymentPort(Protocol):
    pass

  @Adapter(PaymentPort, key='primary', envs={'prod'})
  class StripePaymentAdapter(PaymentPort):
    pass

  @Adapter(PaymentPort, key='primary', envs={'test'})
  class FakePaymentAdapter(PaymentPort):
    pass

  table.register_adapter(StripePaymentAdapter)
  table.register_adapter(FakePaymentAdapter)

  assert isinstance(table.resolve(PaymentPort, key='primary'), StripePaymentAdapter)


def test_duplicate_key_with_overlapping_environments_raises() -> None:
  table = Wiring(environment='prod')

  @Port
  class PaymentPort(Protocol):
    pass

  @Adapter(PaymentPort, key='primary', envs={'prod'})
  class StripePaymentAdapter(PaymentPort):
    pass

  @Adapter(PaymentPort, key='primary', envs={'prod'})
  class BraintreePaymentAdapter(PaymentPort):
    pass

  table.register_adapter(StripePaymentAdapter)

  with pytest.raises(InvalidAdapterError):
    table.register_adapter(BraintreePaymentAdapter)


def test_duplicate_unkeyed_adapters_in_overlapping_envs_raises() -> None:
  table = Wiring(environment='prod')

  @Port
  class PaymentPort(Protocol):
    pass

  # Two unkeyed adapters (both key=None) active in 'prod' collide via key-overlap.
  @Adapter(PaymentPort, envs={'prod'})
  class StripePaymentAdapter(PaymentPort):
    pass

  @Adapter(PaymentPort, envs={'prod'})
  class BraintreePaymentAdapter(PaymentPort):
    pass

  table.register_adapter(StripePaymentAdapter)

  with pytest.raises(InvalidAdapterError):
    table.register_adapter(BraintreePaymentAdapter)


def test_invalid_adapter_does_not_satisfy_port() -> None:
  table = Wiring()

  @Port
  class AppleBasketPort(Protocol):
    def take_apple(self) -> str: ...

  @Adapter(AppleBasketPort)
  class RockBasketAdapter:
    pass

  table.register_adapter(RockBasketAdapter)

  with pytest.raises(InvalidAdapterError):
    table.resolve(AppleBasketPort)


def test_missing_explicit_key_raises() -> None:
  table = Wiring()

  @Port
  class AppleBasketPort(Protocol):
    pass

  @Adapter(AppleBasketPort, key='golden')
  class GoldenAppleBasketAdapter(AppleBasketPort):
    pass

  table.register_adapter(GoldenAppleBasketAdapter)

  with pytest.raises(AdapterNotFoundError):
    table.resolve(AppleBasketPort, key='orchard')


def test_non_port_resolution_raises() -> None:
  table = Wiring()

  class NotAPort:
    pass

  with pytest.raises(InvalidPortError):
    table.resolve(NotAPort)


def test_constructor_parameter_without_type_hint_raises() -> None:
  table = Wiring()

  @Port
  class ServicePort(Protocol):
    pass

  @Adapter(ServicePort)
  class ServiceAdapter(ServicePort):
    def __init__(self, dependency) -> None:  # type: ignore[no-untyped-def]
      self.dependency = dependency

  table.register_adapter(ServiceAdapter)

  with pytest.raises(MissingTypeHintError):
    table.resolve(ServicePort)


def test_constructor_cycle_raises() -> None:
  table = Wiring()

  @Port
  class FirstPort(Protocol):
    pass

  @Port
  class SecondPort(Protocol):
    pass

  @Adapter(FirstPort)
  class FirstAdapter(FirstPort):
    def __init__(self, second: SecondPort) -> None:
      self.second = second

  @Adapter(SecondPort)
  class SecondAdapter(SecondPort):
    def __init__(self, first: FirstPort) -> None:
      self.first = first

  table.register_adapter(FirstAdapter)
  table.register_adapter(SecondAdapter)

  with pytest.raises(InjectionCycleError):
    table.resolve(FirstPort)


def test_constructor_optional_dependency_falls_back_when_absent() -> None:
  table = Wiring()

  @Port
  class SidecarPort(Protocol):
    def ping(self) -> str: ...

  @Port
  class ServicePort(Protocol):
    def run(self) -> str: ...

  @Adapter(ServicePort)
  class ServiceAdapter(ServicePort):
    def __init__(self, sidecar: SidecarPort | None = None) -> None:
      self._sidecar = sidecar

    def run(self) -> str:
      return 'no-sidecar' if self._sidecar is None else self._sidecar.ping()

  table.register_adapter(ServiceAdapter)  # no SidecarPort adapter is registered

  assert table.resolve(ServicePort).run() == 'no-sidecar'


def test_constructor_optional_dependency_injects_when_present() -> None:
  table = Wiring()

  @Port
  class SidecarPort(Protocol):
    def ping(self) -> str: ...

  @Adapter(SidecarPort)
  class SidecarAdapter(SidecarPort):
    def ping(self) -> str:
      return 'pong'

  @Port
  class ServicePort(Protocol):
    def run(self) -> str: ...

  @Adapter(ServicePort)
  class ServiceAdapter(ServicePort):
    def __init__(self, sidecar: SidecarPort | None = None) -> None:
      self._sidecar = sidecar

    def run(self) -> str:
      return 'none' if self._sidecar is None else self._sidecar.ping()

  table.register_adapter(SidecarAdapter)
  table.register_adapter(ServiceAdapter)

  assert table.resolve(ServicePort).run() == 'pong'


def test_structural_adapter_without_inheriting_the_port_resolves() -> None:
  # Python 3.11 counts any attribute stored on a Protocol as a member, so a port marker kept in
  # the Protocol's namespace would make every structural adapter fail the isinstance check.
  table = Wiring()

  @Port
  class GreeterPort(Protocol):
    def hello(self) -> str: ...

  @Adapter(GreeterPort)
  class StructuralGreeterAdapter:
    def hello(self) -> str:
      return 'hi'

  table.register_adapter(StructuralGreeterAdapter)

  assert table.resolve(GreeterPort).hello() == 'hi'


def test_adapter_subclassing_its_port_is_not_itself_a_port() -> None:
  # Only the exact class decorated with @Port is a port; subclasses never inherit the badge.
  @Port
  class GreeterPort(Protocol):
    def hello(self) -> str: ...

  @Adapter(GreeterPort)
  class GreeterAdapter(GreeterPort):
    def hello(self) -> str:
      return 'hi'

  with pytest.raises(InvalidPortError):
    Adapter(GreeterAdapter)


def test_resolving_an_undecorated_protocol_subclass_of_a_port_is_rejected() -> None:
  table = Wiring()

  @Port
  class GreeterPort(Protocol):
    def hello(self) -> str: ...

  class LouderGreeterPort(GreeterPort, Protocol):
    def shout(self) -> str: ...

  with pytest.raises(InvalidPortError):
    table.resolve(LouderGreeterPort)
