"""Engine-level resolution through ``Wiring``: selection, lifecycles, optional ports, cycles, plans.
Adapter constructors decorated with ``@Invert`` get their own keys and map honoured here, while
undecorated ones resolve unkeyed, and each adapter's plan is worked out once until ``clear()``.
"""

from typing import Protocol, cast

import pytest

from idunn import (
  Adapter,
  AdapterNotFoundError,
  InjectionCycleError,
  InvalidAdapterError,
  InvalidPortError,
  Invert,
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
  local = f'{__name__}.test_duplicate_key_with_overlapping_environments_raises.<locals>'

  # Both culprits by full name: two Stripe adapters in two modules would otherwise look identical.
  with pytest.raises(InvalidAdapterError) as collision:
    table.register_adapter(BraintreePaymentAdapter)

  assert f'{local}.PaymentPort' in str(collision.value)
  assert f'{local}.StripePaymentAdapter and {local}.BraintreePaymentAdapter' in str(collision.value)


def test_duplicate_unkeyed_adapters_in_overlapping_envs_raises() -> None:
  table = Wiring(environment='prod')

  @Port
  class PaymentPort(Protocol):
    pass

  # Two unkeyed adapters both active in 'prod': same (port, key=None), overlapping envs.
  @Adapter(PaymentPort, envs={'prod'})
  class StripePaymentAdapter(PaymentPort):
    pass

  @Adapter(PaymentPort, envs={'prod'})
  class BraintreePaymentAdapter(PaymentPort):
    pass

  table.register_adapter(StripePaymentAdapter)

  with pytest.raises(InvalidAdapterError, match=r'StripePaymentAdapter and .*BraintreePayment'):
    table.register_adapter(BraintreePaymentAdapter)


@pytest.mark.parametrize('order', ['agnostic-first', 'scoped-first'])
def test_an_env_agnostic_adapter_collides_with_a_scoped_one(order: str) -> None:
  # Agnostic means active everywhere, prod included: letting both in would make prod a guess.
  @Port
  class PaymentPort(Protocol):
    pass

  @Adapter(PaymentPort)
  class AnywherePayment(PaymentPort):
    pass

  @Adapter(PaymentPort, envs={'prod'})
  class ProdPayment(PaymentPort):
    pass

  pair = (
    (AnywherePayment, ProdPayment) if order == 'agnostic-first' else (ProdPayment, AnywherePayment)
  )

  with pytest.raises(InvalidAdapterError, match='overlapping environments'):
    Wiring.of(*pair)


def test_a_missing_adapter_names_its_port_key_and_environment() -> None:
  table = Wiring(environment='prod')

  @Port
  class PaymentPort(Protocol):
    pass

  local = f'{__name__}.test_a_missing_adapter_names_its_port_key_and_environment.<locals>'

  with pytest.raises(AdapterNotFoundError) as unkeyed:
    table.resolve(PaymentPort)
  with pytest.raises(AdapterNotFoundError) as keyed:
    table.resolve(PaymentPort, key='nope')

  assert str(unkeyed.value).endswith(f"port {local}.PaymentPort in 'prod'.")
  assert str(keyed.value).endswith(f"port {local}.PaymentPort with key 'nope' in 'prod'.")


def test_invalid_adapter_does_not_satisfy_port() -> None:
  table = Wiring()

  @Port
  class AppleBasketPort(Protocol):
    def take_apple(self) -> str: ...

  @Adapter(AppleBasketPort)
  class RockBasketAdapter:
    pass

  table.register_adapter(RockBasketAdapter)
  local = f'{__name__}.test_invalid_adapter_does_not_satisfy_port.<locals>'

  with pytest.raises(InvalidAdapterError) as mismatch:
    table.resolve(AppleBasketPort)

  assert f'{local}.RockBasketAdapter does not satisfy port {local}.AppleBasketPort' in str(
    mismatch.value
  )


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

  with pytest.raises(InvalidPortError) as refused:
    table.resolve(NotAPort)

  assert str(refused.value).endswith(
    f'{__name__}.test_non_port_resolution_raises.<locals>.NotAPort'
  )


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

  with pytest.raises(MissingTypeHintError) as missing:
    table.resolve(ServicePort)

  local = f'{__name__}.test_constructor_parameter_without_type_hint_raises.<locals>'
  assert str(missing.value).endswith(f'{local}.ServiceAdapter.dependency')


def test_constructor_parameter_typed_as_a_plain_value_raises() -> None:
  table = Wiring()

  @Port
  class ServicePort(Protocol):
    pass

  @Adapter(ServicePort)
  class ServiceAdapter(ServicePort):
    def __init__(self, label: str) -> None:
      self.label = label

  table.register_adapter(ServiceAdapter)

  # Idunn injects ports, never values; a str with no default has nobody to supply it.
  with pytest.raises(MissingTypeHintError) as refused:
    table.resolve(ServicePort)

  local = f'{__name__}.test_constructor_parameter_typed_as_a_plain_value_raises.<locals>'
  assert f'{local}.ServiceAdapter.label: builtins.str is not an @Port' in str(refused.value)


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

  with pytest.raises(InjectionCycleError) as cycle:
    table.resolve(FirstPort)

  local = f'{__name__}.test_constructor_cycle_raises.<locals>'
  assert str(cycle.value).endswith(
    f'{local}.FirstAdapter -> {local}.SecondAdapter -> {local}.FirstAdapter'
  )


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


def test_an_adapter_port_with_a_non_none_default_gets_that_default_when_absent() -> None:
  # Any default makes a port optional, not only None: the default is what the adapter asked for.
  @Port
  class SidecarPort(Protocol):
    def ping(self) -> str: ...

  class SpareSidecar:
    def ping(self) -> str:
      return 'spare'

  spare = SpareSidecar()

  @Port
  class ServicePort(Protocol):
    def run(self) -> str: ...

  @Adapter(ServicePort)
  class ServiceAdapter(ServicePort):
    def __init__(self, sidecar: SidecarPort = spare) -> None:
      self.sidecar: SidecarPort = sidecar

    def run(self) -> str:
      return self.sidecar.ping()

  assert Wiring.of(ServiceAdapter).resolve(ServicePort).sidecar is spare


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

  with pytest.raises(InvalidPortError, match=r'not marked with @Port: .*\.GreeterAdapter$'):
    Adapter(GreeterAdapter)


def test_resolving_an_undecorated_protocol_subclass_of_a_port_is_rejected() -> None:
  table = Wiring()

  @Port
  class GreeterPort(Protocol):
    def hello(self) -> str: ...

  class LouderGreeterPort(GreeterPort, Protocol):
    def shout(self) -> str: ...

  with pytest.raises(InvalidPortError, match=r'not marked with @Port: .*\.LouderGreeterPort$'):
    table.resolve(LouderGreeterPort)


def test_an_optional_adapter_parameter_without_a_default_gets_none_when_absent() -> None:
  table = Wiring()

  @Port
  class SidecarPort(Protocol):
    def ping(self) -> str: ...

  @Port
  class ServicePort(Protocol):
    def run(self) -> str: ...

  @Adapter(ServicePort)
  class ServiceAdapter(ServicePort):
    def __init__(self, sidecar: SidecarPort | None) -> None:
      self.sidecar = sidecar

    def run(self) -> str:
      return 'run'

  table.register_adapter(ServiceAdapter)

  assert table.resolve(ServicePort).sidecar is None


@Port
class NotifierPort(Protocol):
  def send(self) -> str: ...


@Port
class ReminderPort(Protocol):
  def remind(self) -> str: ...


# One port, an unkeyed email adapter and a keyed sms one: the silent-wrong-injection setup.
@Adapter(NotifierPort)
class EmailNotifier:
  def send(self) -> str:
    return 'email'


@Adapter(NotifierPort, key='sms')
class SmsNotifier:
  def send(self) -> str:
    return 'sms'


def test_an_adapter_constructor_keyed_with_invert_gets_its_keyed_dependency() -> None:
  @Adapter(ReminderPort)
  class Reminder:
    notifier: NotifierPort

    @Invert(keys={'notifier': 'sms'})
    def __init__(self, *, notifier: NotifierPort) -> None:
      pass

    def remind(self) -> str:
      return self.notifier.send()

  # 1.x handed this constructor the unkeyed email adapter: wrong, and silent about it.
  table = Wiring.of(EmailNotifier, SmsNotifier, Reminder)

  assert table.resolve(ReminderPort).remind() == 'sms'


def test_an_adapter_constructor_with_an_explicit_map_gets_its_dependency() -> None:
  @Adapter(ReminderPort)
  class Reminder:
    @Invert({'notifier': NotifierPort})
    def __init__(self, *, notifier: object) -> None:
      self._notifier = notifier

    def remind(self) -> str:
      return cast(NotifierPort, self._notifier).send()

  table = Wiring.of(EmailNotifier, Reminder)

  assert table.resolve(ReminderPort).remind() == 'email'


def test_plain_invert_and_undecorated_adapter_constructors_resolve_unkeyed() -> None:
  @Adapter(ReminderPort)
  class PlainReminder:
    @Invert()
    def __init__(self, *, notifier: NotifierPort) -> None:
      self._notifier = notifier

    def remind(self) -> str:
      return self._notifier.send()

  @Adapter(ReminderPort, key='bare')
  class BareReminder:
    def __init__(self, notifier: NotifierPort) -> None:
      self._notifier = notifier

    def remind(self) -> str:
      return self._notifier.send()

  keyed_only = Wiring.of(SmsNotifier, PlainReminder, BareReminder)
  both = Wiring.of(SmsNotifier, EmailNotifier, PlainReminder, BareReminder)

  # A keyed adapter never sneaks into a constructor that did not ask for it by name.
  with pytest.raises(AdapterNotFoundError):
    keyed_only.resolve(ReminderPort)
  with pytest.raises(AdapterNotFoundError):
    keyed_only.resolve(ReminderPort, key='bare')
  assert both.resolve(ReminderPort).remind() == 'email'
  assert both.resolve(ReminderPort, key='bare').remind() == 'email'


def test_a_cycle_through_a_keyed_dependency_is_still_a_cycle() -> None:
  @Port
  class EggPort(Protocol):
    pass

  @Port
  class HenPort(Protocol):
    pass

  @Adapter(EggPort, key='first')
  class Egg:
    def __init__(self, hen: HenPort) -> None:
      self.hen = hen

  @Adapter(HenPort)
  class Hen:
    @Invert(keys={'egg': 'first'})
    def __init__(self, *, egg: EggPort) -> None:
      pass

  table = Wiring.of(Egg, Hen)

  with pytest.raises(InjectionCycleError) as cycle:
    table.resolve(HenPort)

  local = f'{__name__}.test_a_cycle_through_a_keyed_dependency_is_still_a_cycle.<locals>'
  assert str(cycle.value).endswith(f'{local}.Hen -> {local}.Egg -> {local}.Hen')


def test_an_adapter_plan_is_made_once_and_forgotten_on_clear() -> None:
  table = Wiring.of(EmailNotifier)

  table.resolve(NotifierPort)
  plan = table.resolver._plans[EmailNotifier]
  table.resolve(NotifierPort)

  assert table.resolver._plans[EmailNotifier] is plan
  table.resolver.clear()
  assert table.resolver._plans == {}


def test_a_positional_only_port_on_an_adapter_raises_type_error() -> None:
  @Adapter(ReminderPort)
  class Reminder:
    def __init__(self, notifier: NotifierPort, /) -> None:
      self._notifier = notifier

    def remind(self) -> str:
      return self._notifier.send()

  table = Wiring.of(EmailNotifier, Reminder)

  with pytest.raises(TypeError, match=r'Reminder\.notifier is a positional-only port'):
    table.resolve(ReminderPort)
