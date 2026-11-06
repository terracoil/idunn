"""``@Invert(bootstrap=...)``: a library that wires itself the first time a consumer needs it.
The wrapper calls the public ``Idunn().bootstrap(root)`` after the positional check and the plan,
before anything is injected, and only when a planned port is missing from the call. So these tests
watch three things: whether discovery ran (the gate's report cache, and whether the package's
adapters module was ever imported), what the consumer received, and what happened first. The
import-time and thread tests belong to the concurrency set: run them ten times per interpreter.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Mapping
from functools import partial
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol

import pytest

from idunn import (
  Adapter,
  DiscoveryError,
  Idunn,
  InvalidAdapterError,
  Invert,
  LifecycleEnum,
  Port,
  ReportMap,
)
from idunn.testing import Harness

from _support import ImportingCall, PackageWriter, Racer, Resolve

# Never importable, so any bootstrap of it raises: a wrapper that bootstraps where it should not
# fails the test out loud instead of quietly finding nothing.
NOWHERE = 'invert_bootstrap_nowhere'


@Port
class BasketPort(Protocol):
  def take(self) -> str: ...


@Port
class SagaPort(Protocol):
  def tell(self) -> str: ...


@Port
class HornPort(Protocol):
  def blow(self) -> str: ...


@Port
class CellarPort(Protocol):
  def serve(self) -> str: ...


@Adapter(BasketPort)
class GoldenBasket(BasketPort):
  def take(self) -> str:
    return 'golden'


class QuietHorn(HornPort):
  """Not an adapter: the default a defaulted port parameter falls back to."""

  def blow(self) -> str:
    return 'silence'


QUIET = QuietHorn()


class CellarBody:
  """What both cellars share: three planned ports, one required, one optional, one defaulted.
  Nothing but ``basket`` is ever active, so the resolver must hand over the two fallbacks itself.
  If it ever left one out for Python to default, the wrapper would see a port missing and
  bootstrap ``NOWHERE``, which raises.
  """

  basket: BasketPort
  saga: SagaPort | None
  horn: HornPort

  def serve(self) -> str:
    return f'{self.basket.take()}, {self.saga}, {self.horn.blow()}'


@Adapter(CellarPort, lifecycle=LifecycleEnum.SINGLETON)
class SingletonCellar(CellarBody):
  @Invert(bootstrap=NOWHERE)
  def __init__(
    self, *, basket: BasketPort, saga: SagaPort | None = None, horn: HornPort = QUIET
  ) -> None:
    pass


@Adapter(CellarPort, key='transient')
class TransientCellar(CellarBody):
  @Invert(bootstrap=NOWHERE)
  def __init__(
    self, *, basket: BasketPort, saga: SagaPort | None = None, horn: HornPort = QUIET
  ) -> None:
    pass


class FakeBasket:
  """A stand-in for the library's basket, structurally a port."""

  def take_apple(self) -> str:
    return 'a wax apple'


class Library:
  """Writes a small library whose consumers all wear ``@Invert(bootstrap=<its own root>)``."""

  PORTS = """
    from typing import Protocol
    from idunn import Port

    @Port
    class AppleBasketPort(Protocol):
        def take_apple(self) -> str: ...

    @Port
    class SagaPort(Protocol):
        def tell(self) -> str: ...
  """
  ADAPTERS = """
    from idunn import Adapter, LifecycleEnum
    from {package}.ports import AppleBasketPort, SagaPort

    @Adapter(AppleBasketPort, lifecycle=LifecycleEnum.SINGLETON)
    class GoldenBasket(AppleBasketPort):
        def take_apple(self) -> str:
            return "golden apple from {package}"

    @Adapter(SagaPort)
    class Skald(SagaPort):
        def tell(self) -> str:
            return "a saga"
  """
  API = """
    from idunn import Invert
    from {package}.ports import AppleBasketPort, SagaPort

    class QuietSaga:
        def tell(self) -> str:
            return "silence"

    QUIET_SAGA = QuietSaga()

    class Feast:
        basket: AppleBasketPort
        saga: SagaPort | None

        @Invert(bootstrap="{package}")
        def __init__(self, *, basket: AppleBasketPort, saga: SagaPort | None = None) -> None:
            pass

    class SideFeast(Feast):
        def __init__(self) -> None:
            super().__init__()

    class WildFeast:
        @Invert(keys={{"basket": "wild"}}, bootstrap="{package}")
        def __init__(self, *, basket: AppleBasketPort) -> None:
            pass

    class MappedFeast:
        @Invert({{"basket": AppleBasketPort}}, bootstrap="{package}")
        def __init__(self, *, basket) -> None:
            pass

    @Invert(bootstrap="{package}")
    def harvest(*, basket: AppleBasketPort) -> str:
        return basket.take_apple()

    @Invert(bootstrap="{package}")
    def recite(*, basket: AppleBasketPort, saga: SagaPort | None = None) -> str:
        return "no saga" if saga is None else saga.tell()

    @Invert(bootstrap="{package}")
    def chant(*, basket: AppleBasketPort, saga: SagaPort = QUIET_SAGA) -> str:
        return saga.tell()

    class Orchard:
        @Invert(bootstrap="{package}")
        def pick(self, *, basket: AppleBasketPort) -> str:
            return basket.take_apple()

        @staticmethod
        @Invert(bootstrap="{package}")
        def gather(*, basket: AppleBasketPort) -> str:
            return basket.take_apple()

        @classmethod
        @Invert(bootstrap="{package}")
        def stock(cls, *, basket: AppleBasketPort) -> str:
            return basket.take_apple()
  """
  # Only for the test that wants a keyed adapter: the others' reports stay two adapters long.
  WILD = """
    from idunn import Adapter
    from {package}.ports import AppleBasketPort

    @Adapter(AppleBasketPort, key="wild")
    class WildBasket(AppleBasketPort):
        def take_apple(self) -> str:
            return "wild apple"
  """

  @classmethod
  def install(
    cls, writer: PackageWriter, package: str, *, extra: Mapping[str, str] | None = None
  ) -> ModuleType:
    """Write the library (plus ``extra`` files, formatted alike) and return its ``api`` module."""
    sources: dict[str, str] = {
      'ports.py': cls.PORTS,
      'adapters.py': cls.ADAPTERS,
      'api.py': cls.API,
      **(extra or {}),
    }
    writer.package(
      package, {name: source.format(package=package) for name, source in sources.items()}
    )
    return importlib.import_module(f'{package}.api')

  @staticmethod
  def apple(package: str) -> str:
    """Return what the library's basket says."""
    return f'golden apple from {package}'


class Memory:
  """What the gate remembers and what discovery left behind, read without changing either."""

  @staticmethod
  def reports() -> Mapping[str, ReportMap]:
    """Return the gate's cached reports, from the read-only snapshot ``Harness`` takes."""
    return Idunn()._snapshot().reports

  @staticmethod
  def discovered(package: str) -> bool:
    """Whether discovery ever imported the package's adapters; nothing else imports them."""
    return f'{package}.adapters' in sys.modules


class Calls:
  """Records each call to one ``Idunn`` method by the root it names, then calls straight through."""

  def __init__(self, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Wrap ``Idunn.<name>`` for the length of the test."""
    self.roots: list[str] = []
    original: Callable[..., ReportMap] = getattr(Idunn, name)

    def counted(container: Idunn, root_package: str, **options: Any) -> ReportMap:
      self.roots.append(root_package)  # list.append is atomic, so racing threads all count
      return original(container, root_package, **options)

    monkeypatch.setattr(Idunn, name, counted)


class Deferred:
  """A consumer module whose hints name ``LaterPort`` and ``LaterValue``, which the test supplies."""

  SOURCE = """
    from __future__ import annotations
    from idunn import Invert

    @Invert(bootstrap="{package}")
    def pick(*, basket: LaterPort) -> str:
        return basket.take_apple()

    @Invert(bootstrap="{package}")
    def positional(basket: LaterPort) -> str:
        return basket.take()

    class Positional:
        @Invert(bootstrap="{package}")
        def __init__(self, basket: LaterPort) -> None:
            pass

    @Invert(bootstrap="{package}")
    def labelled(*, label: LaterValue) -> str:
        return label
  """

  @classmethod
  def load(cls, writer: PackageWriter, name: str, package: str) -> ModuleType:
    """Write the consumers as top-level module ``name``, bootstrapping ``package``, and import it."""
    writer.module(name, cls.SOURCE.format(package=package))
    return importlib.import_module(name)


# First use: every wrapper form discovers its root, once.


@pytest.mark.parametrize('name', ['Feast', 'SideFeast'], ids=['own', 'super-init'])
def test_constructing_a_consumer_discovers_its_library_and_injects_it(
  writer: PackageWriter, name: str
) -> None:
  # SideFeast's undecorated __init__ only calls super().__init__(), whose wrapper does the work.
  package = f'ib_construct_{name.lower()}'
  api = Library.install(writer, package)
  assert not Memory.discovered(package)  # decoration imported nothing

  feast = getattr(api, name)()

  assert feast.basket.take_apple() == Library.apple(package)
  assert feast.saga.tell() == 'a saga'
  assert Memory.reports()[package]['registered_adapters'] == (
    f'{package}.adapters.GoldenBasket',
    f'{package}.adapters.Skald',
  )


@pytest.mark.parametrize('form', ['function', 'method', 'static method', 'class method'])
def test_calling_a_function_or_any_kind_of_method_discovers_too(
  writer: PackageWriter, form: str
) -> None:
  package = f'ib_call_{form.replace(" ", "_")}'
  api = Library.install(writer, package)
  calls: dict[str, Callable[[], str]] = {
    'function': api.harvest,
    'method': api.Orchard().pick,
    'static method': api.Orchard.gather,
    'class method': api.Orchard.stock,
  }

  assert calls[form]() == Library.apple(package)
  assert package in Memory.reports()


def test_a_second_construction_is_a_cache_hit(
  writer: PackageWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
  package = 'ib_cache_hit'
  api = Library.install(writer, package)
  discoveries = Calls(monkeypatch, 'autodiscover')
  api.Feast()
  report = Memory.reports()[package]

  assert api.Feast().basket.take_apple() == Library.apple(package)
  assert discoveries.roots == [package]
  assert Idunn().bootstrap(package) is report


def test_an_explicit_bootstrap_with_options_goes_first_and_the_consumer_hits_its_cache(
  writer: PackageWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
  # The documented recipe for a library that needs options: bootstrap= cannot pass them, so the
  # entry point calls bootstrap itself, first, and the first call is the one whose options count.
  package = 'ib_options_first'
  api = Library.install(
    writer,
    package,
    extra={
      'heavy.py': 'raise RuntimeError("excluded, so never imported")',
      'flaky.py': 'raise RuntimeError("skipped, since strict=False")',
    },
  )

  report = Idunn().bootstrap(package, exclude='heavy', strict=False)
  discoveries = Calls(monkeypatch, 'autodiscover')

  assert f'{package}.heavy' not in sys.modules
  assert report['skipped_modules'] == (f'{package}.flaky',)
  assert api.Feast().basket.take_apple() == Library.apple(package)
  assert discoveries.roots == []
  assert Memory.reports()[package] is report


@pytest.mark.parametrize('form', ['constructor', 'function'])
def test_the_wrapper_bootstraps_once_per_call_however_many_ports_are_missing(
  writer: PackageWriter, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
  package = f'ib_once_per_call_{form}'
  api = Library.install(writer, package)
  consumer: Callable[[], object] = api.Feast if form == 'constructor' else api.recite
  calls = Calls(monkeypatch, 'bootstrap')

  consumer()  # basket and saga both missing
  consumer()

  assert calls.roots == [package, package]


def test_consumers_naming_different_roots_each_discover_only_their_own(
  writer: PackageWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
  first, second = 'ib_root_one', 'ib_root_two'
  api_one, api_two = Library.install(writer, first), Library.install(writer, second)
  discoveries = Calls(monkeypatch, 'autodiscover')

  api_one.Feast()
  assert not Memory.discovered(second)
  for feast in (api_two.Feast, api_one.Feast, api_two.Feast):
    feast()

  assert discoveries.roots == [first, second]
  assert set(Memory.reports()) == {first, second}


def test_a_namespace_package_root_is_discovered(writer: PackageWriter) -> None:
  package = 'ib_space_ns'  # the _ns suffix keeps PackageWriter from writing its __init__.py
  api = Library.install(writer, package)
  assert getattr(sys.modules[package], '__file__', None) is None

  assert api.Feast().basket.take_apple() == Library.apple(package)
  assert Memory.reports()[package]['registered_adapters'] == (
    f'{package}.adapters.GoldenBasket',
    f'{package}.adapters.Skald',
  )


# Only a missing port sets it off.


def test_supplying_every_port_runs_no_discovery(writer: PackageWriter) -> None:
  package = 'ib_all_supplied'
  api = Library.install(writer, package)
  basket, saga = FakeBasket(), object()

  feast = api.Feast(basket=basket, saga=saga)

  assert (feast.basket, feast.saga) == (basket, saga)
  assert api.harvest(basket=basket) == 'a wax apple'
  assert api.Feast(basket=basket, saga=None).saga is None  # an explicit None is still supplied
  assert api.Feast(basket=None, saga=None).basket is None  # for a required port too
  assert package not in Memory.reports()
  assert not Memory.discovered(package)


def test_supplying_some_ports_still_discovers(writer: PackageWriter) -> None:
  package = 'ib_some_supplied'
  api = Library.install(writer, package)

  feast = api.Feast(saga=None)

  assert feast.basket.take_apple() == Library.apple(package)
  assert package in Memory.reports()


@pytest.mark.parametrize('form', ['constructor', 'function', 'defaulted'])
def test_an_optional_port_alone_missing_still_discovers(writer: PackageWriter, form: str) -> None:
  # Discovery is what decides whether an adapter exists, so "optional" is no reason to skip it,
  # in either spelling: `Port | None`, or a port with a default (chant's would say "silence").
  package = f'ib_optional_missing_{form}'
  api = Library.install(writer, package)
  calls: dict[str, Callable[[], str]] = {
    'constructor': lambda: api.Feast(basket=FakeBasket()).saga.tell(),
    'function': lambda: api.recite(basket=FakeBasket()),
    'defaulted': lambda: api.chant(basket=FakeBasket()),
  }

  assert calls[form]() == 'a saga'
  assert package in Memory.reports()


def test_a_consumer_whose_ports_are_all_optional_discovers_and_receives_none(
  writer: PackageWriter,
) -> None:
  package = 'ib_optional_only'
  Library.install(writer, package)

  @Invert(bootstrap=package)
  def listen(*, horn: HornPort | None = None) -> HornPort | None:
    return horn

  assert listen() is None  # the library has no horn, which only discovery could say
  assert package in Memory.reports()


@pytest.mark.parametrize(
  ('name', 'apple'), [('WildFeast', 'wild apple'), ('MappedFeast', None)], ids=['keyed', 'mapped']
)
def test_a_keyed_or_mapped_port_discovers_and_receives_its_adapter(
  writer: PackageWriter, name: str, apple: str | None
) -> None:
  package = f'ib_{name.lower()}'
  api = Library.install(writer, package, extra={'wild.py': Library.WILD})

  assert getattr(api, name)().basket.take_apple() == (apple or Library.apple(package))
  assert package in Memory.reports()


def test_plain_invert_and_bootstrap_none_never_touch_the_gate(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  calls = Calls(monkeypatch, 'bootstrap')

  class Plain:
    basket: BasketPort

    @Invert()
    def __init__(self, *, basket: BasketPort) -> None:
      pass

  @Invert(bootstrap=None)
  def pick(*, basket: BasketPort) -> str:
    return basket.take()

  with Harness.install(GoldenBasket):
    assert Plain().basket.take() == pick() == 'golden'

  assert calls.roots == []
  assert dict(Memory.reports()) == {}


# Order: positionals, plan, bootstrap, inject.


@pytest.mark.parametrize('form', ['constructor', 'function', 'method', 'static method'])
def test_too_many_positionals_raise_before_discovery(writer: PackageWriter, form: str) -> None:
  package = f'ib_too_many_{form.replace(" ", "_")}'
  api = Library.install(writer, package)
  calls: dict[str, Callable[[], object]] = {
    'constructor': lambda: api.Feast(FakeBasket()),
    'function': lambda: api.harvest(FakeBasket()),
    'method': lambda: api.Orchard().pick(FakeBasket()),  # self is the one positional it takes
    'static method': lambda: api.Orchard.gather(FakeBasket()),
  }

  with pytest.raises(TypeError, match=r'positional arguments? but \d (was|were) given'):
    calls[form]()

  assert not Memory.discovered(package)


@pytest.mark.parametrize('name', ['positional', 'Positional'], ids=['function', 'constructor'])
def test_a_deferred_planning_error_raises_before_discovery(
  writer: PackageWriter, name: str
) -> None:
  package = f'ib_deferred_error_{name.lower()}'
  Library.install(writer, package)
  module = Deferred.load(writer, f'{package}_consumer', package)
  vars(module)['LaterPort'] = BasketPort

  with pytest.raises(TypeError, match="port parameter 'basket' must be keyword-only"):
    getattr(module, name)(GoldenBasket())

  assert not Memory.discovered(package)


def test_a_forward_reference_resolved_at_the_first_call_bootstraps_then(
  writer: PackageWriter,
) -> None:
  package = 'ib_forward'
  Library.install(writer, package)
  ports = importlib.import_module(f'{package}.ports')
  module = Deferred.load(writer, 'ib_forward_consumer', package)
  vars(module)['LaterPort'] = ports.AppleBasketPort

  assert module.pick() == Library.apple(package)
  assert package in Memory.reports()


# Failures propagate, touch nothing, and are retried.


@pytest.mark.parametrize(
  ('state', 'error', 'match'),
  [('missing', ModuleNotFoundError, 'ib_root_missing'), ('raising', RuntimeError, 'flooded')],
  ids=['missing', 'raising'],
)
def test_a_root_that_will_not_import_raises_at_the_first_call_touches_nothing_and_recovers(
  writer: PackageWriter, state: str, error: type[Exception], match: str
) -> None:
  # The root's own import error comes out as is: discovery wraps only the modules beneath it.
  root = f'ib_root_{state}'
  built: list[str] = []
  flooded: Path | None = (
    writer.package(root, {'__init__.py': 'raise RuntimeError("the cellar flooded")'})
    if state == 'raising'
    else None
  )

  @Adapter(BasketPort, key='counted')
  class CountedBasket(BasketPort):
    def __init__(self) -> None:
      built.append('basket')

    def take(self) -> str:
      return 'counted'

  class Feast:
    basket: BasketPort
    horn: HornPort

    @Invert(keys={'basket': 'counted'}, bootstrap=root)
    def __init__(self, *, basket: BasketPort, horn: HornPort) -> None:
      built.append('feast')  # must wait for a bootstrap that works

  with Harness.install(CountedBasket):
    feast = Feast.__new__(Feast)
    with pytest.raises(error, match=match):
      Feast.__init__(feast, horn=QUIET)

    assert vars(feast) == {}  # not even the horn the caller handed over
    assert built == []
    assert root not in Memory.reports()
    if flooded is None:
      writer.package(root, {})  # the root exists now, and holds nothing
    else:  # a different size, so a bytecode cache from the same second cannot pass for it
      (flooded / '__init__.py').write_text('# dry again, nothing to raise\n', encoding='utf-8')
      importlib.invalidate_caches()

    assert Feast(horn=QUIET).basket.take() == 'counted'  # the same consumer, the next call
    assert built == ['basket', 'feast']
    assert Memory.reports()[root]['root_package'] == root


@pytest.mark.parametrize('form', ['constructor', 'function'])
def test_a_discovery_error_propagates_unwrapped_and_the_next_call_retries(
  writer: PackageWriter, form: str
) -> None:
  # Unwrapped, and from the default options: strict=False would have skipped the module quietly.
  package = f'ib_broken_{form}'
  api = Library.install(writer, package, extra={'broken.py': 'raise RuntimeError("not yet")'})
  calls: dict[str, Callable[[], str]] = {
    'constructor': lambda: api.Feast().basket.take_apple(),
    'function': api.harvest,
  }

  with pytest.raises(DiscoveryError, match='broken'):
    calls[form]()
  assert package not in Memory.reports()

  (Path(str(api.__file__)).parent / 'broken.py').unlink()
  importlib.invalidate_caches()

  assert calls[form]() == Library.apple(package)
  assert package in Memory.reports()


def test_reset_forgets_the_root_so_the_next_call_discovers_again(writer: PackageWriter) -> None:
  package = 'ib_reset'
  api = Library.install(writer, package)
  api.Feast()
  first = Memory.reports()[package]

  Idunn().reset(environment='local')
  assert package not in Memory.reports()

  assert api.Feast().basket.take_apple() == Library.apple(package)
  second = Memory.reports()[package]
  assert second is not first
  assert second == first


def test_an_override_wins_and_the_block_restores_bootstrap_memory(writer: PackageWriter) -> None:
  package = 'ib_override'
  api = Library.install(writer, package)
  ports = importlib.import_module(f'{package}.ports')
  fake = FakeBasket()

  with Harness.override(ports.AppleBasketPort, fake):
    feast = api.Feast()  # the saga is still missing, so the library is discovered all the same

    assert feast.basket is fake
    assert feast.saga.tell() == 'a saga'
    assert package in Memory.reports()

  assert package not in Memory.reports()
  assert api.Feast().basket.take_apple() == Library.apple(package)


def test_installing_a_rival_for_a_librarys_port_collides_and_an_override_is_the_way_in(
  writer: PackageWriter,
) -> None:
  # Discovery runs inside whatever block is open, so the library's own adapter lands in the slot
  # the rival holds. An override on top changes nothing: the port is still left to injection.
  package = 'ib_install_rival'
  api = Library.install(writer, package)
  ports = importlib.import_module(f'{package}.ports')

  class WaxBasket(FakeBasket):
    pass

  rival: type[Any] = Adapter(ports.AppleBasketPort)(WaxBasket)

  with Harness.install(rival):
    with pytest.raises(InvalidAdapterError, match=r'WaxBasket and .*GoldenBasket'):
      api.Feast()
    with Harness.override(ports.AppleBasketPort, FakeBasket()):
      with pytest.raises(InvalidAdapterError, match=r'WaxBasket and .*GoldenBasket'):
        api.Feast()
    assert package not in Memory.reports()  # a collision caches nothing

  assert api.Feast().basket.take_apple() == Library.apple(package)
  # Once the root is discovered, the rival collides at the install instead.
  with pytest.raises(InvalidAdapterError, match=r'GoldenBasket and .*WaxBasket'):
    with Harness.install(rival):
      pass  # never reached: the install raises on entry


# The resolver passes every planned port, so a dependency build never bootstraps.


@pytest.mark.parametrize('key', [None, 'transient'], ids=['singleton', 'transient'])
def test_an_adapter_wearing_bootstrap_is_built_by_the_resolver_without_a_gate_call(
  monkeypatch: pytest.MonkeyPatch, key: str | None
) -> None:
  calls = Calls(monkeypatch, 'bootstrap')
  with Harness.install(GoldenBasket, SingletonCellar, TransientCellar):
    # The trap is armed: called by hand with a port missing, the constructor does bootstrap.
    with pytest.raises(ModuleNotFoundError, match=NOWHERE):
      SingletonCellar()
    calls.roots.clear()

    cellar = Resolve.port(CellarPort, key)

    assert cellar.serve() == 'golden, None, silence'
    assert cellar.horn is QUIET
  assert calls.roots == []
  assert NOWHERE not in Memory.reports()


@pytest.mark.parametrize('lifecycle', [LifecycleEnum.SINGLETON, LifecycleEnum.TRANSIENT])
def test_a_consumer_built_inside_an_adapter_constructor_discovers_its_root_mid_build(
  writer: PackageWriter, lifecycle: LifecycleEnum
) -> None:
  # Single-threaded, so the singleton's lock held across discovery costs nothing here; ADVANCED's
  # thread-safety fine print covers the two-thread case.
  package = f'ib_inside_{lifecycle.name.lower()}'
  api = Library.install(writer, package)

  @Adapter(HornPort, lifecycle=lifecycle)
  class FeastHorn(HornPort):
    def __init__(self) -> None:
      self.feast: Any = api.Feast()

    def blow(self) -> str:
      return str(self.feast.basket.take_apple())

  with Harness.install(FeastHorn):
    assert Resolve.port(HornPort).blow() == Library.apple(package)
    assert package in Memory.reports()


# Import time: the wrapper inherits the gate's rules, so it behaves like the explicit call.


class ImportTime:
  """Library modules that build a consumer from their own module body."""

  FEAST_AT_IMPORT = """
    from {package}.api import Feast

    FEAST = Feast()
  """
  SYNC = """
    import threading

    a_started = threading.Event()
    late_entered = threading.Event()
  """
  # The owner's discovery parks here until the importer is inside its import of `late`. The owner
  # then needs `late`'s module lock, which the importer holds, so the importer's bootstrap must
  # not wait for the owner's flight: that is exactly the deadlock the gate exists to avoid.
  PARK = """
    import {sync}

    {sync}.a_started.set()
    {sync}.late_entered.wait(5)
  """


def test_a_module_building_a_consumer_mid_discovery_reenters_without_deadlock(
  writer: PackageWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
  package = 'ib_reentry'
  api = Library.install(writer, package, extra={'feasting.py': ImportTime.FEAST_AT_IMPORT})
  discoveries = Calls(monkeypatch, 'autodiscover')

  # On a Racer thread: a gate that waited on its own flight would hang, not fail.
  feast = Racer(timeout=10).call(api.Feast)

  nested = importlib.import_module(f'{package}.feasting').FEAST
  assert discoveries.roots == [package, package]  # the outer run, and the re-entry's own
  assert feast.basket is nested.basket  # one singleton between the two
  assert feast.basket.take_apple() == Library.apple(package)
  assert Memory.reports()[package]['registered_adapters'] == (
    f'{package}.adapters.GoldenBasket',
    f'{package}.adapters.Skald',
  )


def test_importing_a_module_that_builds_a_consumer_discovers_without_recursing(
  writer: PackageWriter,
) -> None:
  package = 'ib_import_builds'
  Library.install(writer, package, extra={'feasting.py': ImportTime.FEAST_AT_IMPORT})

  # Discovery imports `feasting` again while it is still importing: it must get the module back.
  feasting = Racer(timeout=10).call(partial(importlib.import_module, f'{package}.feasting'))

  assert feasting.FEAST.basket.take_apple() == Library.apple(package)
  assert len(Memory.reports()[package]['registered_adapters']) == 2


def test_a_consumer_built_mid_import_on_another_thread_joins_the_flight_instead_of_waiting(
  writer: PackageWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
  package, sync_name = 'ib_cross_thread', 'ib_cross_thread_sync'
  writer.module(sync_name, ImportTime.SYNC)
  sync = importlib.import_module(sync_name)
  api = Library.install(
    writer,
    package,
    extra={'a.py': ImportTime.PARK.replace('{sync}', sync_name), 'late.py': ''},
  )

  def enter_then_build() -> object:
    sync.late_entered.set()
    return api.Feast()

  # Claims `late` ahead of its file, so the body runs from a loader with no module-body frame.
  importing = ImportingCall(f'{package}.late', enter_then_build)
  discoveries = Calls(monkeypatch, 'autodiscover')

  def import_once_the_owner_parks() -> object:
    assert sync.a_started.wait(5)
    return importing.run()

  racer = Racer(timeout=10)
  with importing.installed():
    racer.start('owner', api.Feast)
    racer.start('importer', import_once_the_owner_parks)
    racer.join()

  assert racer.raised == {}
  # The owner cannot finish without `late`, so the importer always found the flight open: it ran
  # a discovery of its own rather than waiting on one that was waiting on it.
  assert discoveries.roots == [package, package]
  owner, importer = racer.results['owner'], racer.results['importer']
  assert owner.basket is importer.basket  # type: ignore[attr-defined]
  assert owner.basket.take_apple() == Library.apple(package)  # type: ignore[attr-defined]
  assert Memory.reports()[package]['registered_adapters'] == (
    f'{package}.adapters.GoldenBasket',
    f'{package}.adapters.Skald',
  )


# Threads: concurrent first uses share one discovery and one singleton.


@pytest.mark.usefixtures('eager_switching')
def test_concurrent_first_constructions_share_one_discovery_and_one_singleton(
  writer: PackageWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
  package = 'ib_threads'
  api = Library.install(writer, package)
  discoveries = Calls(monkeypatch, 'autodiscover')
  thread_count = 8
  racer = Racer(timeout=10)

  racer.run(*(api.Feast for _ in range(thread_count)))

  assert racer.errors == []
  baskets = {id(feast.basket) for feast in racer.results.values()}  # type: ignore[attr-defined]
  assert len(racer.results) == thread_count
  assert len(baskets) == 1
  assert discoveries.roots == [package]
  assert Idunn().bootstrap(package) is Memory.reports()[package]


# No ports, no bootstrap=: a root that could never be discovered from is refused, not ignored.


def test_bootstrap_on_a_function_with_no_ports_raises_at_decoration() -> None:
  with pytest.raises(TypeError, match=r"bootstrap='my_lib'\) on .*\.greet has no port parameters"):

    @Invert(bootstrap='my_lib')
    def greet(name: str, *, punctuation: str = '!') -> str:
      return f'Hail, {name}{punctuation}'


def test_bootstrap_with_no_ports_behind_a_forward_reference_raises_at_every_call(
  writer: PackageWriter,
) -> None:
  package = 'ib_idle'
  Library.install(writer, package)
  module = Deferred.load(writer, 'ib_idle_consumer', package)
  vars(module)['LaterValue'] = str

  for _ in range(2):  # a failure is never cached as a plan
    with pytest.raises(TypeError, match='has no port parameters'):
      module.labelled(label='mead')

  assert not Memory.discovered(package)
