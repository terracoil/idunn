import importlib
import sys
from pathlib import Path
from textwrap import dedent
from typing import Protocol

import pytest
from idunn.app import Adapter, Idunn, Port
from idunn.domain import (
  AdapterNotFoundError,
  InjectionCycleError,
  InvalidAdapterError,
  InvalidPortError,
  LifecycleEnum,
  MissingTypeHintError,
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


def test_autodiscover_imports_decorated_adapters_under_adapters_package(
  tmp_path: Path,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  package_name = 'sample_app_one'
  _write_package(
    tmp_path=tmp_path,
    package_name=package_name,
    files={
      'ports.py': """
                from typing import Protocol
                from idunn.app import Port

                @Port
                class AppleBasketPort(Protocol):
                    def take_apple(self) -> str: ...
            """,
      'adapters/__init__.py': '',
      'adapters/apple.py': """
                from idunn.app import Adapter
                from sample_app_one.ports import AppleBasketPort

                @Adapter(AppleBasketPort)
                class GoldenAppleBasketAdapter(AppleBasketPort):
                    def take_apple(self) -> str:
                        return "golden apple"
            """,
    },
  )
  monkeypatch.syspath_prepend(str(tmp_path))
  importlib.invalidate_caches()

  table = Idunn()
  report = table.autodiscover(package_name)
  ports = importlib.import_module(f'{package_name}.ports')
  basket = table._inject(ports.AppleBasketPort)

  assert basket.take_apple() == 'golden apple'
  assert report['imported_adapter_modules'] == (
    f'{package_name}.adapters',
    f'{package_name}.adapters.apple',
  )
  assert len(report['registered_adapters']) == 1
  # The adapter subclasses its port but must NOT be mis-registered as a port.
  assert report['registered_ports'] == (f'{package_name}.ports.AppleBasketPort',)


def test_autodiscover_finds_nested_adapters_packages(
  tmp_path: Path,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  package_name = 'sample_app_two'
  _write_package(
    tmp_path=tmp_path,
    package_name=package_name,
    files={
      'ports.py': """
                from typing import Protocol
                from idunn.app import Port

                @Port
                class PaymentPort(Protocol):
                    def charge(self) -> str: ...
            """,
      'billing/__init__.py': '',
      'billing/adapters/__init__.py': '',
      'billing/adapters/payment.py': """
                from idunn.app import Adapter
                from sample_app_two.ports import PaymentPort

                @Adapter(PaymentPort)
                class StripePaymentAdapter(PaymentPort):
                    def charge(self) -> str:
                        return "stripe"
            """,
    },
  )
  monkeypatch.syspath_prepend(str(tmp_path))
  importlib.invalidate_caches()

  table = Idunn()
  report = table.autodiscover(package_name)
  ports = importlib.import_module(f'{package_name}.ports')
  payment = table._inject(ports.PaymentPort)

  assert payment.charge() == 'stripe'
  assert f'{package_name}.billing.adapters.payment' in report['imported_modules']


def test_autodiscover_does_not_register_undecorated_classes(
  tmp_path: Path,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  package_name = 'sample_app_three'
  _write_package(
    tmp_path=tmp_path,
    package_name=package_name,
    files={
      'ports.py': """
                from typing import Protocol
                from idunn.app import Port

                @Port
                class AppleBasketPort(Protocol):
                    def take_apple(self) -> str: ...
            """,
      'adapters/__init__.py': '',
      'adapters/apple.py': """
                from sample_app_three.ports import AppleBasketPort

                class PlainAppleBasketAdapter(AppleBasketPort):
                    def take_apple(self) -> str:
                        return "plain apple"
            """,
    },
  )
  monkeypatch.syspath_prepend(str(tmp_path))
  importlib.invalidate_caches()

  table = Idunn()
  report = table.autodiscover(package_name)
  ports = importlib.import_module(f'{package_name}.ports')

  with pytest.raises(AdapterNotFoundError):
    table._inject(ports.AppleBasketPort)
  assert report['registered_adapters'] == ()


def test_autodiscover_does_not_import_non_adapter_modules(
  tmp_path: Path,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  package_name = 'sample_app_four'
  _write_package(
    tmp_path=tmp_path,
    package_name=package_name,
    files={
      'ports.py': """
                from typing import Protocol
                from idunn.app import Port

                @Port
                class AppleBasketPort(Protocol):
                    pass
            """,
      'service.py': """
                raise RuntimeError("service module should not be imported")
            """,
      'adapters/__init__.py': '',
      'adapters/apple.py': """
                from idunn.app import Adapter
                from sample_app_four.ports import AppleBasketPort

                @Adapter(AppleBasketPort)
                class AppleBasketAdapter(AppleBasketPort):
                    pass
            """,
    },
  )
  monkeypatch.syspath_prepend(str(tmp_path))
  importlib.invalidate_caches()

  table = Idunn()
  table.autodiscover(package_name)

  assert f'{package_name}.service' not in sys.modules


def test_idunn_facade_can_autodiscover_and_resolve(
  tmp_path: Path,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  package_name = 'sample_app_five'
  _write_package(
    tmp_path=tmp_path,
    package_name=package_name,
    files={
      'ports.py': """
                from typing import Protocol
                from idunn.app import Port

                @Port
                class AppleBasketPort(Protocol):
                    def take_apple(self) -> str: ...
            """,
      'adapters/__init__.py': '',
      'adapters/apple.py': """
                from idunn.app import Adapter
                from sample_app_five.ports import AppleBasketPort

                @Adapter(AppleBasketPort)
                class AppleBasketAdapter(AppleBasketPort):
                    def take_apple(self) -> str:
                        return "facade apple"
            """,
    },
  )
  monkeypatch.syspath_prepend(str(tmp_path))
  importlib.invalidate_caches()
  Idunn().reset()

  Idunn().autodiscover(package_name)
  ports = importlib.import_module(f'{package_name}.ports')
  basket = Idunn()._inject(ports.AppleBasketPort)

  assert basket.take_apple() == 'facade apple'


def test_autodiscover_imports_and_registers_ports_without_adapters(
  tmp_path: Path,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  package_name = 'sample_app_six'
  _write_package(
    tmp_path=tmp_path,
    package_name=package_name,
    files={
      'ports.py': """
                from typing import Protocol
                from idunn.app import Port

                @Port
                class AppleBasketPort(Protocol):
                    def take_apple(self) -> str: ...
            """,
    },
  )
  monkeypatch.syspath_prepend(str(tmp_path))
  importlib.invalidate_caches()

  table = Idunn()
  report = table.autodiscover(package_name)

  assert report['imported_port_modules'] == (f'{package_name}.ports',)
  assert report['registered_ports'] == (f'{package_name}.ports.AppleBasketPort',)
  assert report['registered_adapters'] == ()


def test_autodiscover_registers_all_adapters_before_constructor_injection(
  tmp_path: Path,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  package_name = 'sample_app_seven'
  _write_package(
    tmp_path=tmp_path,
    package_name=package_name,
    files={
      'ports.py': """
                from typing import Protocol
                from idunn.app import Port

                @Port
                class AppleBasketPort(Protocol):
                    def take_apple(self) -> str: ...

                @Port
                class FeastPort(Protocol):
                    def serve(self) -> str: ...
            """,
      'adapters/__init__.py': '',
      'adapters/feast.py': """
                from idunn.app import Adapter
                from sample_app_seven.ports import AppleBasketPort, FeastPort

                constructed = 0

                @Adapter(FeastPort)
                class FeastAdapter(FeastPort):
                    def __init__(self, basket: AppleBasketPort) -> None:
                        global constructed
                        constructed += 1
                        self._basket = basket

                    def serve(self) -> str:
                        return f"feast with {self._basket.take_apple()}"
            """,
      'adapters/z_apple.py': """
                from idunn.app import Adapter
                from sample_app_seven.ports import AppleBasketPort

                constructed = 0

                @Adapter(AppleBasketPort)
                class GoldenAppleBasketAdapter(AppleBasketPort):
                    def __init__(self) -> None:
                        global constructed
                        constructed += 1

                    def take_apple(self) -> str:
                        return "golden apple"
            """,
    },
  )
  monkeypatch.syspath_prepend(str(tmp_path))
  importlib.invalidate_caches()

  table = Idunn()
  report = table.autodiscover(package_name)
  ports = importlib.import_module(f'{package_name}.ports')
  feast_module = importlib.import_module(f'{package_name}.adapters.feast')
  apple_module = importlib.import_module(f'{package_name}.adapters.z_apple')

  assert feast_module.constructed == 0
  assert apple_module.constructed == 0
  assert report['registered_adapters'] == (
    f'{package_name}.adapters.feast.FeastAdapter',
    f'{package_name}.adapters.z_apple.GoldenAppleBasketAdapter',
  )

  feast = table._inject(ports.FeastPort)

  assert feast.serve() == 'feast with golden apple'
  assert feast_module.constructed == 1
  assert apple_module.constructed == 1


def test_autodiscover_does_not_import_unrelated_packages_while_scanning(
  tmp_path: Path,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  package_name = 'sample_app_eight'
  _write_package(
    tmp_path=tmp_path,
    package_name=package_name,
    files={
      'ports.py': """
                from typing import Protocol
                from idunn.app import Port

                @Port
                class AppleBasketPort(Protocol):
                    pass
            """,
      'analytics/__init__.py': """
                raise RuntimeError("analytics package should not be imported")
            """,
      'analytics/reports.py': """
                raise RuntimeError("reports module should not be imported")
            """,
      'adapters/__init__.py': '',
      'adapters/apple.py': """
                from idunn.app import Adapter
                from sample_app_eight.ports import AppleBasketPort

                @Adapter(AppleBasketPort)
                class AppleBasketAdapter(AppleBasketPort):
                    pass
            """,
    },
  )
  monkeypatch.syspath_prepend(str(tmp_path))
  importlib.invalidate_caches()

  table = Idunn()
  table.autodiscover(package_name)

  assert f'{package_name}.analytics' not in sys.modules
  assert f'{package_name}.analytics.reports' not in sys.modules


def _write_package(*, tmp_path: Path, package_name: str, files: dict[str, str]) -> None:
  package_dir = tmp_path / package_name
  package_dir.mkdir()
  (package_dir / '__init__.py').write_text('', encoding='utf-8')
  for relative_path, content in files.items():
    path = package_dir / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.name == '__init__.py' and not content:
      path.write_text('', encoding='utf-8')
    else:
      path.write_text(dedent(content).strip() + '\n', encoding='utf-8')
