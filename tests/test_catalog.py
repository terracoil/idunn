"""The copy-on-write ``Catalog`` behind ``InversionMapper``: lookups, atomic batches, threads.
Selection used to be a memo that registration had to remember to invalidate. Now every
registration swaps in a whole new snapshot, so "is the cache stale?" has no question left to
answer, and the tests below check what replaced it: per-environment lookups, all-or-nothing
batches, and readers that never see a half-built catalog.
"""

import sys
import threading
import time
from collections.abc import Iterator
from functools import partial
from typing import Any, Protocol

import pytest
from idunn import Adapter, AdapterNotFoundError, InvalidAdapterError, InvalidPortError, Port
from idunn.domain import Catalog, PortBinding
from idunn.internal import InversionMapper


@Port
class GreeterPort(Protocol):
  def hello(self) -> str: ...


@Port
class LampPort(Protocol):
  def shine(self) -> str: ...


class BareProtocol(Protocol):
  """A Protocol nobody marked with @Port."""

  def shine(self) -> str: ...


@Adapter(GreeterPort, envs={'prod'})
class ProdGreeter(GreeterPort):
  def hello(self) -> str:
    return 'prod'


@Adapter(GreeterPort, envs={'test'})
class SandboxGreeter(GreeterPort):
  def hello(self) -> str:
    return 'test'


@Adapter(GreeterPort, key='gold')
class GoldGreeter(GreeterPort):
  def hello(self) -> str:
    return 'gold'


@Adapter(GreeterPort)
class AnyGreeter(GreeterPort):
  def hello(self) -> str:
    return 'any'


@Adapter(GreeterPort)
class RivalGreeter(GreeterPort):
  """Unkeyed and env-agnostic, exactly like ``AnyGreeter``: the two can never share a catalog."""

  def hello(self) -> str:
    return 'rival'


@Adapter(LampPort)
class OilLamp(LampPort):
  def shine(self) -> str:
    return 'flicker'


class PlainGreeter:
  """An undecorated class — never marked with @Adapter."""

  def hello(self) -> str:
    return 'plain'


class Greeters:
  """Mints distinct keyed ``GreeterPort`` adapters, for tests that need more than a handful."""

  @staticmethod
  def keyed(*keys: str) -> tuple[type[Any], ...]:
    """Return one freshly decorated adapter class per key."""
    return tuple(
      Adapter(GreeterPort, key=key)(
        type(f'Greeter_{key}', (), {'hello': lambda self: type(self).__name__})
      )
      for key in keys
    )


class Racer:
  """Runs callables on threads started together and collects whatever they raise."""

  def __init__(self) -> None:
    """Start with no errors recorded."""
    self.errors: list[BaseException] = []

  def run(self, *targets: Any) -> None:
    """Start every target behind one barrier, then wait for all of them.
    A thread still running after the timeout is recorded as an error, and threads are daemons, so
    a deadlock fails the test instead of hanging pytest at exit.
    """
    barrier = threading.Barrier(len(targets))
    threads = [
      threading.Thread(target=self._guarded, args=(barrier, target), daemon=True)
      for target in targets
    ]
    for thread in threads:
      thread.start()
    for thread in threads:
      thread.join(timeout=30)
    self.errors.extend(
      TimeoutError(f'{thread.name} still running after 30 s')
      for thread in threads
      if thread.is_alive()
    )

  def _guarded(self, barrier: threading.Barrier, target: Any) -> None:
    try:
      barrier.wait()
      target()
    except BaseException as error:  # the assertion is that this list stays empty
      self.errors.append(error)


@pytest.fixture
def eager_switching() -> Iterator[None]:
  """Make the interpreter swap threads every microsecond, so races show up in a test this short."""
  previous = sys.getswitchinterval()
  sys.setswitchinterval(1e-6)
  yield
  sys.setswitchinterval(previous)


def test_selection_is_scoped_per_environment() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(ProdGreeter)
  mapper.register_adapter(SandboxGreeter)

  prod = mapper.select(port=GreeterPort, key=None, environment='prod')
  test = mapper.select(port=GreeterPort, key=None, environment='test')

  assert prod.adapter is ProdGreeter
  assert test.adapter is SandboxGreeter
  assert mapper.find(port=GreeterPort, key=None, environment='local') is None


def test_find_returns_the_registered_metadata() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(ProdGreeter)

  found = mapper.find(port=GreeterPort, key=None, environment='prod')

  assert found is mapper.catalog.adapters[ProdGreeter]


def test_a_registration_is_visible_to_every_later_lookup() -> None:
  mapper = InversionMapper()
  assert mapper.find(port=GreeterPort, key=None, environment='prod') is None
  mapper.register_adapter(ProdGreeter)
  hit = mapper.find(port=GreeterPort, key=None, environment='prod')
  assert hit is not None and hit.adapter is ProdGreeter

  mapper.register_adapter(GoldGreeter)

  # Nothing to invalidate: the new snapshot simply has both, and the earlier hit still stands.
  keyed = mapper.find(port=GreeterPort, key='gold', environment='prod')
  assert keyed is not None and keyed.adapter is GoldGreeter
  assert mapper.find(port=GreeterPort, key=None, environment='prod') is hit


def test_keyed_and_unkeyed_live_in_separate_slots() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(AnyGreeter)
  mapper.register_adapter(GoldGreeter)

  unkeyed = mapper.find(port=GreeterPort, key=None, environment='local')
  keyed = mapper.find(port=GreeterPort, key='gold', environment='local')

  assert unkeyed is not None and unkeyed.adapter is AnyGreeter
  assert keyed is not None and keyed.adapter is GoldGreeter
  assert set(mapper.catalog.slots) == {(GreeterPort, None), (GreeterPort, 'gold')}


def test_env_agnostic_adapter_answers_every_environment() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(AnyGreeter)

  local = mapper.find(port=GreeterPort, key=None, environment='local')
  prod = mapper.find(port=GreeterPort, key=None, environment='prod')
  test = mapper.find(port=GreeterPort, key=None, environment='test')

  assert local is not None
  assert local is prod is test
  assert local.adapter is AnyGreeter


def test_clear_swaps_in_an_empty_catalog() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(AnyGreeter)
  before = mapper.catalog

  mapper.clear()

  assert mapper.catalog == Catalog.empty()
  assert len(before.adapters) == 1  # whoever held the old snapshot keeps it intact
  mapper.register_adapter(ProdGreeter)
  again = mapper.find(port=GreeterPort, key=None, environment='prod')
  assert again is not None and again.adapter is ProdGreeter


def test_idempotent_reregistration_returns_false() -> None:
  mapper = InversionMapper()

  assert mapper.register_adapter(ProdGreeter) is True
  before = mapper.catalog
  assert mapper.register_adapter(ProdGreeter) is False

  assert mapper.ports == frozenset({GreeterPort})
  assert mapper.catalog is before  # nothing new, nothing swapped


def test_select_raises_with_and_without_key_message() -> None:
  mapper = InversionMapper()

  with pytest.raises(AdapterNotFoundError) as unkeyed:
    mapper.select(port=GreeterPort, key=None, environment='local')
  with pytest.raises(AdapterNotFoundError) as keyed:
    mapper.select(port=GreeterPort, key='nope', environment='local')

  assert 'with key' not in str(unkeyed.value)
  assert f"{__name__}.GreeterPort with key 'nope'" in str(keyed.value)


def test_register_adapter_on_undecorated_class_raises() -> None:
  mapper = InversionMapper()

  with pytest.raises(InvalidAdapterError, match=f'{__name__}.PlainGreeter$'):
    mapper.register_adapter(PlainGreeter)


def test_a_registration_leaves_the_previous_snapshot_unchanged() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(ProdGreeter)
  before = mapper.catalog

  mapper.register_batch(ports=(LampPort,), adapters=(GoldGreeter,))

  assert mapper.catalog is not before
  assert before.ports == frozenset({GreeterPort})
  assert list(before.adapters) == [ProdGreeter]
  assert set(before.slots) == {(GreeterPort, None)}
  assert before.find(port=GreeterPort, key='gold', environment='local') is None


def test_bindings_keep_registration_order() -> None:
  mapper = InversionMapper()
  for adapter in (SandboxGreeter, GoldGreeter, ProdGreeter):
    mapper.register_adapter(adapter)

  (binding,) = mapper.bindings(environment='test')

  assert [metadata.adapter for metadata in binding.adapters] == [
    SandboxGreeter,
    GoldGreeter,
    ProdGreeter,
  ]
  assert binding.selected is not None and binding.selected.adapter is SandboxGreeter


def test_batch_reports_only_what_it_added() -> None:
  mapper = InversionMapper()

  first = mapper.register_batch(
    ports=(LampPort, LampPort), adapters=(AnyGreeter, GoldGreeter, AnyGreeter)
  )
  second = mapper.register_batch(ports=(LampPort, GreeterPort), adapters=(GoldGreeter,))

  # GreeterPort arrived implicitly with its adapters, so it was never "new" to report.
  assert first == ((LampPort,), (AnyGreeter, GoldGreeter))
  assert second == ((), ())
  assert mapper.ports == frozenset({LampPort, GreeterPort})


def test_batch_with_a_collision_inside_it_registers_nothing() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(OilLamp)
  before_ports = mapper.ports
  before_bindings = mapper.bindings(environment='local')

  # RivalGreeter, third in line, collides with AnyGreeter, first in line.
  with pytest.raises(InvalidAdapterError, match='AnyGreeter and .*RivalGreeter'):
    mapper.register_batch(ports=(GreeterPort,), adapters=(AnyGreeter, GoldGreeter, RivalGreeter))

  assert mapper.ports == before_ports == frozenset({LampPort})
  assert mapper.bindings(environment='local') == before_bindings


def test_batch_colliding_with_an_earlier_registration_registers_nothing() -> None:
  mapper = InversionMapper()
  mapper.register_adapter(AnyGreeter)
  before = mapper.catalog

  with pytest.raises(InvalidAdapterError, match='AnyGreeter and .*RivalGreeter'):
    mapper.register_batch(adapters=(GoldGreeter, RivalGreeter))

  assert mapper.catalog is before
  assert mapper.find(port=GreeterPort, key='gold', environment='local') is None
  assert mapper.register_adapter(GoldGreeter) is True  # and the failed batch let go of the lock


def test_batch_with_an_unmarked_port_registers_nothing() -> None:
  mapper = InversionMapper()

  with pytest.raises(InvalidPortError, match=f'{__name__}.BareProtocol$'):
    mapper.register_batch(ports=(LampPort, BareProtocol), adapters=(AnyGreeter,))

  assert mapper.catalog == Catalog.empty()


@pytest.mark.usefixtures('eager_switching')
def test_concurrent_registration_never_shows_readers_a_broken_catalog() -> None:
  mapper = InversionMapper()
  batches = [Greeters.keyed(*(f'w{writer}k{index}' for index in range(40))) for writer in range(4)]
  writers_done = threading.Event()
  deadline = time.monotonic() + 0.2

  def write(adapters: tuple[type[Any], ...]) -> None:
    for adapter in adapters:  # one swap per adapter, to give readers plenty to trip over
      mapper.register_adapter(adapter)

  def read() -> None:
    seen = 0
    while not writers_done.is_set() or time.monotonic() < deadline:
      bindings: tuple[PortBinding, ...] = mapper.bindings(environment='local')
      count = sum(len(binding.adapters) for binding in bindings)
      assert count >= seen, 'a newer snapshot lost adapters'
      seen = count
      mapper.find(port=GreeterPort, key='w0k0', environment='local')

  def write_all() -> None:
    writers = Racer()
    writers.run(*(lambda batch=batch: write(batch) for batch in batches))
    writers_done.set()
    assert not writers.errors, writers.errors

  racer = Racer()
  racer.run(write_all, read, read, read, read)

  assert not racer.errors, racer.errors
  assert len(mapper.catalog.adapters) == 160
  for adapter in (adapter for batch in batches for adapter in batch):
    key = mapper.catalog.adapters[adapter].key
    assert mapper.find(port=GreeterPort, key=key, environment='local') is not None


@pytest.mark.usefixtures('eager_switching')
def test_concurrent_batches_of_the_same_classes_register_them_once() -> None:
  adapters: tuple[type[Any], ...] = (
    GoldGreeter,
    ProdGreeter,
    SandboxGreeter,
    *Greeters.keyed(*map(str, range(200))),
  )

  def register(mapper: InversionMapper, results: list[Any]) -> None:
    results.append(mapper.register_batch(ports=(GreeterPort,), adapters=adapters))

  for _ in range(25):
    mapper = InversionMapper()
    results: list[tuple[tuple[type[Any], ...], tuple[type[Any], ...]]] = []
    racer = Racer()

    racer.run(partial(register, mapper, results), partial(register, mapper, results))

    assert not racer.errors, racer.errors
    # Whoever got the lock first registered everything; the other found nothing new.
    assert sorted(results, key=lambda result: len(result[1])) == [
      ((), ()),
      ((GreeterPort,), adapters),
    ]
