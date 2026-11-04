"""``idunn.testing.Harness``: wiring for one block, and not a moment longer.
Every block snapshots the engine on entry and restores it on exit, so each test checks both
halves: what the block makes possible inside it, and that nothing it registered, built, cached or
overrode is still around afterwards. The awkward cases get their own tests: nesting, a singleton
built against a fake, a ``bootstrap`` run mid-install, a ``reset()`` mid-block, a build still
running when its block closes, and one starting while the block is being put away.
"""

import importlib
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import idunn
import pytest
from idunn import (
  Adapter,
  AdapterNotFoundError,
  Idunn,
  InjectionCycleError,
  InvalidAdapterError,
  InvalidPortError,
  Invert,
  LifecycleEnum,
  Port,
  ReportMap,
)
from idunn.domain import Catalog, EngineSnapshot
from idunn.internal import BootstrapGate
from idunn.testing import Harness

from _support import PackageWriter, Racer, Resolve

SINGLETON = LifecycleEnum.SINGLETON
EMPTY = 'Environment: local'  # describe() of a catalog with nothing in it


@Port
class BasketPort(Protocol):
  def take(self) -> str: ...


@Adapter(BasketPort)
class GoldenBasket:
  def take(self) -> str:
    return 'golden'


@Adapter(BasketPort, key='plain')
class PlainBasket:
  def take(self) -> str:
    return 'plain'


@Adapter(BasketPort)
class RivalBasket:  # GoldenBasket's slot, every environment: the two can never be installed together
  def take(self) -> str:
    return 'rival'


class FakeBasket:
  def take(self) -> str:
    return 'fake'


@Port
class LedgerPort(Protocol):
  def note(self) -> str: ...


@Adapter(LedgerPort)
class InkLedger:
  def note(self) -> str:
    return 'ink'


class FakeLedger:
  def note(self) -> str:
    return 'fake ink'


@Port
class ServicePort(Protocol):
  def run(self) -> str: ...


@Adapter(ServicePort)
class BasketService:
  def __init__(self, basket: BasketPort) -> None:
    self.basket = basket

  def run(self) -> str:
    return f'service:{self.basket.take()}'


@Port
class HubPort(Protocol):
  def report(self) -> str: ...


@Adapter(HubPort, lifecycle=SINGLETON)
class Hub:
  def __init__(self, basket: BasketPort, ledger: LedgerPort) -> None:
    self.basket = basket
    self.ledger = ledger

  def report(self) -> str:
    return f'{self.basket.take()}/{self.ledger.note()}'


class Feast:
  basket: BasketPort

  @Invert()
  def __init__(self, *, basket: BasketPort) -> None:
    pass


class KeyedFeast:
  basket: BasketPort

  @Invert(keys={'basket': 'plain'})
  def __init__(self, *, basket: BasketPort) -> None:
    pass


class OptionalFeast:
  basket: BasketPort | None

  @Invert()
  def __init__(self, *, basket: BasketPort | None = None) -> None:
    pass


class ServiceFeast:
  service: ServicePort

  @Invert()
  def __init__(self, *, service: ServicePort) -> None:
    pass


class RacingLock:
  """Stands in for the resolver's override lock and races one resolve against a restore.
  It fires once, just before the swap it guards or just after, which between them put a resolve on
  both sides of every swap the restore makes, whatever order it makes them in.
  """

  def __init__(self, *, race: Callable[[], object], after: bool) -> None:
    self.racer: Racer = Racer(timeout=5)
    self._lock: threading.Lock = threading.Lock()
    self._race: Callable[[], object] | None = race
    self._after: bool = after

  def __enter__(self) -> None:
    """Race now if this lock fires before the swap, then take the lock."""
    if not self._after:
      self._fire()
    self._lock.acquire()

  def __exit__(self, *exc_info: object) -> None:
    """Release the lock, then race if this one fires after the swap."""
    self._lock.release()
    if self._after:
      self._fire()

  def _fire(self) -> None:
    race, self._race = self._race, None
    if race is not None:
      self.racer.run(race)


@pytest.fixture
def writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PackageWriter:
  return PackageWriter(tmp_path=tmp_path, monkeypatch=monkeypatch)


class TestInstall:
  def test_registers_for_the_block_and_forgets_on_exit(self) -> None:
    with Harness.install(GoldenBasket):
      assert Feast().basket.take() == 'golden'
      assert f'selected: {GoldenBasket.__module__}.GoldenBasket' in Idunn().describe()

    assert Idunn().describe() == EMPTY
    with pytest.raises(AdapterNotFoundError):
      Feast()

  def test_a_collision_raises_before_the_block_and_registers_nothing(self) -> None:
    entered: list[bool] = []

    with pytest.raises(InvalidAdapterError, match='Duplicate adapter key'):
      with Harness.install(PlainBasket, GoldenBasket, RivalBasket):
        entered.append(True)

    assert entered == []
    assert Idunn().describe() == EMPTY  # PlainBasket and GoldenBasket did not sneak in either

  def test_a_collision_with_an_outer_block_leaves_the_outer_catalog_alone(self) -> None:
    with Harness.install(GoldenBasket):
      catalog: Catalog = Idunn()._mapper.catalog
      with pytest.raises(InvalidAdapterError):
        with Harness.install(PlainBasket, RivalBasket):
          pass  # never runs: the install raises first

      assert Idunn()._mapper.catalog is catalog
      assert Feast().basket.take() == 'golden'

  def test_a_bootstrap_inside_an_install_leaves_no_report_behind(
    self, writer: PackageWriter
  ) -> None:
    # The block rolls Pear's registration back. Were the cached report to survive it, the second
    # bootstrap would trust the cache, rescan nothing, and leave PearPort with no adapter at all.
    writer.package(
      'harness_orchard',
      {
        'pears.py': """
          from typing import Protocol
          from idunn import Adapter, Port

          @Port
          class PearPort(Protocol):
            def pick(self) -> str: ...

          @Adapter(PearPort)
          class Pear:
            def pick(self) -> str:
              return 'pear'
        """
      },
    )

    with Harness.install(GoldenBasket):
      inside: ReportMap = Idunn().bootstrap('harness_orchard')
    after: ReportMap = Idunn().bootstrap('harness_orchard')

    pears = importlib.import_module('harness_orchard.pears')
    assert inside['registered_adapters'] == ('harness_orchard.pears.Pear',)
    assert after is not inside
    assert after['registered_adapters'] == inside['registered_adapters']
    assert Resolve.port(pears.PearPort).pick() == 'pear'


class TestOverride:
  def test_stands_in_for_a_consumers_port_and_an_adapters_dependency(self) -> None:
    fake = FakeBasket()

    with Harness.install(GoldenBasket, BasketService), Harness.override(BasketPort, fake):
      assert Feast().basket is fake
      assert ServiceFeast().service.run() == 'service:fake'

    with Harness.install(GoldenBasket, BasketService):
      assert ServiceFeast().service.run() == 'service:golden'

  @pytest.mark.parametrize('environment', ['local', 'prod'])
  def test_needs_no_adapter_in_any_environment(self, environment: str) -> None:
    fake = FakeBasket()
    Idunn().reset(environment=environment)

    with Harness.override(BasketPort, fake):
      assert Feast().basket is fake
      assert Resolve.port(BasketPort) is fake

  def test_a_keyed_override_answers_its_key_only(self) -> None:
    fake = FakeBasket()

    with (
      Harness.install(GoldenBasket, PlainBasket),
      Harness.override(BasketPort, fake, key='plain'),
    ):
      assert KeyedFeast().basket is fake
      assert isinstance(Feast().basket, GoldenBasket)

  def test_satisfies_an_optional_port_with_nothing_registered(self) -> None:
    fake = FakeBasket()

    with Harness.override(BasketPort, fake):
      assert OptionalFeast().basket is fake

    assert OptionalFeast().basket is None

  def test_a_caller_supplied_argument_still_wins(self) -> None:
    mine = FakeBasket()

    with Harness.override(BasketPort, FakeBasket()):
      assert Feast(basket=mine).basket is mine

  def test_rejects_a_class_that_is_not_a_port(self) -> None:
    class NotAPort(Protocol):
      def take(self) -> str: ...

    with pytest.raises(InvalidPortError, match='not marked with @Port'):
      with Harness.override(NotAPort, FakeBasket()):
        pass  # never runs: the override raises first

    assert Idunn()._snapshot().overrides == {}

  def test_rejects_an_instance_that_does_not_satisfy_the_port(self) -> None:
    class Stone:
      pass

    with pytest.raises(InvalidAdapterError, match='does not satisfy port'):
      with Harness.override(BasketPort, Stone()):
        pass  # never runs: the override raises first

    assert Idunn()._snapshot().overrides == {}

  def test_nested_overrides_of_one_port_unwind_last_in_first_out(self) -> None:
    first, second = FakeBasket(), FakeBasket()

    with Harness.override(BasketPort, first):
      with Harness.override(BasketPort, second):
        assert Feast().basket is second
      assert Feast().basket is first

    with pytest.raises(AdapterNotFoundError):
      Feast()

  def test_breaks_a_singleton_cycle_for_the_walk_and_the_build(self) -> None:
    # Chicken and egg, settled by bringing a rooster. The walk must treat the override as a leaf,
    # or it would follow HenPort back to Egg and call it a cycle before anything was built.
    built: list[str] = []

    @Port
    class EggPort(Protocol):
      pass

    @Port
    class HenPort(Protocol):
      pass

    @Adapter(EggPort, lifecycle=SINGLETON)
    class Egg:
      def __init__(self, hen: HenPort) -> None:
        built.append('egg')
        self.hen = hen

    @Adapter(HenPort, lifecycle=SINGLETON)
    class Hen:
      def __init__(self, egg: EggPort) -> None:
        built.append('hen')  # never runs: the rooster stands in

    rooster = object()
    with Harness.install(Egg, Hen):
      with pytest.raises(InjectionCycleError):
        Resolve.port(EggPort)
      with Harness.override(HenPort, rooster):
        egg = Resolve.port(EggPort)
      with pytest.raises(InjectionCycleError):
        Resolve.port(EggPort)  # the egg left with the rooster

    assert egg.hen is rooster
    assert built == ['egg']


class TestRestore:
  def test_a_singleton_built_inside_a_block_is_gone_on_exit(self) -> None:
    with Harness.install(GoldenBasket, InkLedger, Hub):
      first = Resolve.port(HubPort)
      assert Resolve.port(HubPort) is first

    with Harness.install(GoldenBasket, InkLedger, Hub):
      assert Resolve.port(HubPort) is not first

  def test_a_singleton_built_against_a_fake_leaves_with_the_fake(self) -> None:
    with Harness.install(GoldenBasket, InkLedger, Hub):
      with Harness.override(BasketPort, FakeBasket()):
        faked = Resolve.port(HubPort)
      real = Resolve.port(HubPort)

    assert faked.report() == 'fake/ink'
    assert real is not faked
    assert real.report() == 'golden/ink'

  def test_nested_overrides_around_a_singleton_restore_fresh_copies(self) -> None:
    # The inner block builds Hub. Its exit must not put that Hub back, and neither must the outer
    # one: a snapshot that kept a live view, or a restore that reused one, would leak it outward.
    with Harness.install(GoldenBasket, InkLedger, Hub):
      with Harness.override(BasketPort, FakeBasket()):
        with Harness.override(LedgerPort, FakeLedger()):
          inner = Resolve.port(HubPort)
        middle = Resolve.port(HubPort)
      outer = Resolve.port(HubPort)

    assert inner.report() == 'fake/fake ink'
    assert middle is not inner
    assert middle.report() == 'fake/ink'
    assert outer is not inner
    assert outer is not middle
    assert outer.report() == 'golden/ink'

  def test_a_reset_inside_a_block_is_undone_on_exit(self) -> None:
    with Harness.install(GoldenBasket, InkLedger, Hub):
      hub = Resolve.port(HubPort)
      with Harness.override(LedgerPort, FakeLedger()):
        Idunn().reset(environment='prod')
        assert Idunn().describe() == 'Environment: prod'
        with pytest.raises(AdapterNotFoundError):
          Resolve.port(LedgerPort)  # reset() forgets overrides too

      assert Idunn().environment == 'local'
      assert Resolve.port(HubPort) is hub  # the very instance, not a rebuild

  def test_an_error_in_the_block_still_restores(self) -> None:
    with pytest.raises(RuntimeError, match='spilled'):
      with Harness.install(GoldenBasket):
        raise RuntimeError('spilled the apples')

    assert Idunn().describe() == EMPTY

  def test_a_build_still_running_at_exit_lands_in_the_discarded_generation(self) -> None:
    # Like reset(), a restore swaps the singleton generation whole, so a build that started before
    # it finishes into a dict nobody reads. Refilling the live dict in place would let it back in.
    started, proceed = threading.Event(), threading.Event()

    @Port
    class SlowPort(Protocol):
      pass

    @Adapter(SlowPort, lifecycle=SINGLETON)
    class Slow:
      def __init__(self) -> None:
        started.set()
        proceed.wait(timeout=5)

    stale: list[object] = []
    builder = threading.Thread(target=lambda: stale.append(Resolve.port(SlowPort)), daemon=True)
    with Harness.install(Slow):
      with Harness.override(BasketPort, FakeBasket()):
        builder.start()
        assert started.wait(timeout=5)
      proceed.set()
      builder.join(timeout=5)
      fresh = Resolve.port(SlowPort)

    assert not builder.is_alive()
    assert stale
    assert fresh is not stale[0]

  @pytest.mark.parametrize('after', [False, True], ids=['before-the-swap', 'after-the-swap'])
  def test_a_resolve_starting_mid_restore_cannot_keep_the_fake(
    self, after: bool, monkeypatch: pytest.MonkeyPatch
  ) -> None:
    # A resolve captures its generation once but reads overrides as it goes, so the restore must
    # put the overrides back first. The other order let a resolve starting between the two swaps
    # build Hub against the departing fake straight into the restored generation, fake and all.
    raced: list[HubPort] = []
    racing = RacingLock(race=lambda: raced.append(Resolve.port(HubPort)), after=after)

    with Harness.install(GoldenBasket, InkLedger, Hub):
      with Harness.override(LedgerPort, FakeLedger()):
        monkeypatch.setattr(Idunn()._resolver, '_override_lock', racing)
      hub = Resolve.port(HubPort)

    assert racing.racer.errors == []
    assert len(raced) == 1
    assert hub.report() == 'golden/ink'


@Harness.install(GoldenBasket)
def test_install_decorates_a_test_function() -> None:
  assert Feast().basket.take() == 'golden'


def test_both_decorate_any_function_and_re_enter_on_every_call() -> None:
  fake = FakeBasket()

  @Harness.install(GoldenBasket, BasketService)
  @Harness.override(BasketPort, fake)
  def serve() -> str:
    return ServiceFeast().service.run()

  assert serve() == 'service:fake'
  assert serve() == 'service:fake'  # a fresh block per call, not a spent generator
  with pytest.raises(AdapterNotFoundError):
    ServiceFeast()


def test_harness_is_not_exported_from_the_root_package() -> None:
  assert not hasattr(idunn, 'Harness')


def test_the_gate_restores_carried_runs_for_the_retry_to_merge() -> None:
  # A failed flight's successful runs stay registered, so a retry would never list their classes
  # as new. The snapshot keeps them waiting, and the restore hands them to the next flight.
  def run(adapter: str) -> ReportMap:
    return {
      'root_package': 'orchard',
      'imported_modules': ('orchard',),
      'skipped_modules': (),
      'registered_ports': (),
      'registered_adapters': (adapter,),
    }

  gate = BootstrapGate()
  carried_run, retry_run = run('orchard.Pear'), run('orchard.Plum')
  gate.restore(
    EngineSnapshot(
      environment='local',
      catalog=Catalog.empty(),
      instances={},
      overrides={},
      reports={},
      carried={'orchard': (carried_run,)},
    )
  )
  reports, carried = gate.snapshot()

  merged = gate.run('orchard', discover=lambda: retry_run)

  assert carried == {'orchard': (carried_run,)}
  assert merged['registered_adapters'] == ('orchard.Pear', 'orchard.Plum')
  assert reports == {}  # a copy: the merge cached since never reaches it
  assert gate.snapshot()[0] == {'orchard': merged}
