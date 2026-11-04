"""Singletons under threads: built once, never queued behind strangers, and cycles caught dry.
A ``SINGLETON`` cache miss walks the graph for cycles without building or locking anything, then
builds under that adapter's own lock and looks again inside it. These tests pin each half: one
instance however many threads ask, unrelated singletons building side by side, a ``reset()`` that a
slow build cannot sneak back into, and a cyclic graph raced from two threads that raises on both
instead of deadlocking.
"""

import threading
import time
from functools import partial
from typing import Protocol

import pytest
from idunn import (
  Adapter,
  AdapterNotFoundError,
  Idunn,
  InjectionCycleError,
  Invert,
  LifecycleEnum,
  Port,
)
from idunn.util import KeyedLocks, QualifiedName

from _support import Container, Racer, Resolve, Wiring

SINGLETON = LifecycleEnum.SINGLETON


class TestKeyedLocks:
  def test_a_key_always_gets_the_same_lock_and_other_keys_get_their_own(self) -> None:
    locks: KeyedLocks[str] = KeyedLocks()

    assert locks.for_key('apple') is locks.for_key('apple')
    assert locks.for_key('apple') is not locks.for_key('pear')

  @pytest.mark.usefixtures('eager_switching')
  def test_threads_asking_for_a_new_key_at_once_share_one_lock(self) -> None:
    for _ in range(25):
      locks: KeyedLocks[str] = KeyedLocks()
      seen: list[object] = []
      racer = Racer(timeout=5)

      racer.run(*(partial(self._grab, locks, seen) for _ in range(8)))

      assert racer.errors == []
      assert len({id(lock) for lock in seen}) == 1

  @staticmethod
  def _grab(locks: KeyedLocks[str], seen: list[object]) -> None:
    seen.append(locks.for_key('apple'))

  def test_the_lock_is_reentrant_for_its_holder(self) -> None:
    lock = KeyedLocks[str]().for_key('apple')

    with lock:
      assert lock.acquire(blocking=False)  # a plain Lock would refuse its own holder
      lock.release()


@pytest.mark.usefixtures('eager_switching')
def test_eight_threads_building_one_singleton_graph_for_the_first_time_get_one_instance() -> None:
  built: list[str] = []

  @Port
  class SettingsPort(Protocol):
    pass

  @Port
  class PoolPort(Protocol):
    pass

  @Adapter(SettingsPort, lifecycle=SINGLETON)
  class Settings:
    def __init__(self) -> None:
      time.sleep(0.02)  # wide enough that every thread misses the cache together
      built.append('settings')

  @Adapter(PoolPort, lifecycle=SINGLETON)
  class Pool:
    def __init__(self, settings: SettingsPort) -> None:
      time.sleep(0.02)
      built.append('pool')
      self.settings = settings

  class Handler:
    @Invert()
    def __init__(self, *, pool: PoolPort) -> None:
      pass

  Container.install(Settings, Pool)
  handlers: list[Handler] = []
  racer = Racer(timeout=10)

  racer.run(*(lambda: handlers.append(Handler()) for _ in range(8)))

  assert racer.errors == []
  assert sorted(built) == ['pool', 'settings']
  pools = {id(handler.pool) for handler in handlers}  # type: ignore[attr-defined]
  assert len(handlers) == 8
  assert len(pools) == 1


def test_transient_instances_stay_distinct_across_threads() -> None:
  @Port
  class CupPort(Protocol):
    pass

  @Adapter(CupPort)
  class Cup:
    pass

  table = Wiring()
  table.register_adapter(Cup)
  cups: list[object] = []
  racer = Racer(timeout=10)

  racer.run(*(lambda: cups.append(table.resolve(CupPort)) for _ in range(8)))

  assert racer.errors == []
  assert len({id(cup) for cup in cups}) == 8


def test_two_unrelated_singletons_build_at_the_same_time() -> None:
  # Each constructor waits until the other has started. If they shared a lock, the first would
  # wait out its timeout alone, so a True from both waits is proof the builds overlapped.
  left_in, right_in = threading.Event(), threading.Event()
  overlapped: dict[str, bool] = {}

  @Port
  class LeftPort(Protocol):
    pass

  @Port
  class RightPort(Protocol):
    pass

  @Adapter(LeftPort, lifecycle=SINGLETON)
  class Left:
    def __init__(self) -> None:
      left_in.set()
      overlapped['left'] = right_in.wait(timeout=5)

  @Adapter(RightPort, lifecycle=SINGLETON)
  class Right:
    def __init__(self) -> None:
      right_in.set()
      overlapped['right'] = left_in.wait(timeout=5)

  table = Wiring()
  table.mapper.register_batch(adapters=(Left, Right))
  racer = Racer(timeout=10)

  racer.run(lambda: table.resolve(LeftPort), lambda: table.resolve(RightPort))

  assert racer.errors == []
  assert overlapped == {'left': True, 'right': True}


def test_a_singleton_constructor_may_join_a_worker_that_builds_another_singleton() -> None:
  # The outer singleton's lock is held while the worker runs; the worker needs a different one.
  @Port
  class InnerPort(Protocol):
    pass

  @Port
  class OuterPort(Protocol):
    pass

  @Adapter(InnerPort, lifecycle=SINGLETON)
  class Inner:
    pass

  class Helper:
    @Invert()
    def __init__(self, *, inner: InnerPort) -> None:
      pass

  @Adapter(OuterPort, lifecycle=SINGLETON)
  class Outer:
    def __init__(self) -> None:
      helpers: list[Helper] = []
      worker = threading.Thread(target=lambda: helpers.append(Helper()), daemon=True)
      worker.start()
      worker.join(timeout=5)
      self.finished: bool = not worker.is_alive()
      self.inner: object = helpers[0].inner if helpers else None  # type: ignore[attr-defined]

  Container.install(Inner, Outer)

  outer = Resolve.port(OuterPort)

  assert outer.finished
  assert outer.inner is Resolve.port(InnerPort)


def test_a_singleton_constructor_may_build_another_singleton_on_its_own_thread() -> None:
  @Port
  class InnerPort(Protocol):
    pass

  @Port
  class OuterPort(Protocol):
    pass

  @Adapter(InnerPort, lifecycle=SINGLETON)
  class Inner:
    pass

  class Helper:
    @Invert()
    def __init__(self, *, inner: InnerPort) -> None:
      pass

  @Adapter(OuterPort, lifecycle=SINGLETON)
  class Outer:
    def __init__(self) -> None:
      self.helper = Helper()  # a fresh resolve, mid-build, for a different singleton

  Container.install(Inner, Outer)

  outer = Resolve.port(OuterPort)

  assert outer.helper.inner is Resolve.port(InnerPort)
  assert Resolve.port(OuterPort) is outer


def test_a_reset_racing_a_singleton_build_keeps_the_stale_instance_out_of_the_new_cache() -> None:
  started, proceed = threading.Event(), threading.Event()
  built: list[object] = []

  @Port
  class SlowPort(Protocol):
    pass

  @Adapter(SlowPort, lifecycle=SINGLETON)
  class Slow:
    def __init__(self) -> None:
      started.set()
      proceed.wait(timeout=5)
      built.append(self)

  Container.install(Slow)
  stale: list[object] = []
  builder = threading.Thread(target=lambda: stale.append(Resolve.port(SlowPort)), daemon=True)
  builder.start()
  assert started.wait(timeout=5)

  Idunn().reset(environment='local')  # mid-build: the builder captured the old generation
  Container.install(Slow)
  proceed.set()
  builder.join(timeout=5)
  fresh = Resolve.port(SlowPort)

  assert not builder.is_alive()
  assert stale and fresh is not stale[0]
  assert Resolve.port(SlowPort) is fresh
  assert len(built) == 2


def test_two_threads_racing_a_cyclic_singleton_graph_both_raise_instead_of_deadlocking() -> None:
  # A and B need each other, and each takes the transient Gate first. Without the dry walk, both
  # threads would build Gate holding their own singleton's lock, meet at the barrier, then wait
  # forever for each other's lock: the barrier makes a regression hang, never pass by luck.
  gate_built: list[object] = []
  barrier = threading.Barrier(2, timeout=5)

  @Port
  class GatePort(Protocol):
    pass

  @Port
  class APort(Protocol):
    pass

  @Port
  class BPort(Protocol):
    pass

  @Adapter(GatePort)
  class Gate:
    def __init__(self) -> None:
      gate_built.append(self)
      barrier.wait()

  @Adapter(APort, lifecycle=SINGLETON)
  class A:
    def __init__(self, gate: GatePort, b: BPort) -> None:
      pass

  @Adapter(BPort, lifecycle=SINGLETON)
  class B:
    def __init__(self, gate: GatePort, a: APort) -> None:
      pass

  table = Wiring()
  table.mapper.register_batch(adapters=(Gate, A, B))
  racer = Racer(timeout=5)

  racer.run(lambda: table.resolve(APort), lambda: table.resolve(BPort))

  assert [type(error) for error in racer.errors] == [InjectionCycleError, InjectionCycleError]
  assert sorted(str(error).rsplit(': ', 1)[1] for error in racer.errors) == [
    ' -> '.join(map(QualifiedName.of, (A, B, A))),
    ' -> '.join(map(QualifiedName.of, (B, A, B))),
  ]
  assert gate_built == []


def test_three_threads_entering_a_three_cycle_at_different_nodes_all_raise() -> None:
  # The loop runs through a keyed edge and an optional one, and each thread starts at a different
  # node, so every walk begins somewhere new. Each node takes the Gate first, as above.
  gate_built: list[object] = []
  barrier = threading.Barrier(3, timeout=5)

  @Port
  class GatePort(Protocol):
    pass

  @Port
  class APort(Protocol):
    pass

  @Port
  class BPort(Protocol):
    pass

  @Port
  class CPort(Protocol):
    pass

  @Adapter(GatePort)
  class Gate:
    def __init__(self) -> None:
      gate_built.append(self)
      barrier.wait()

  @Adapter(APort, lifecycle=SINGLETON)
  class A:
    @Invert(keys={'b': 'first'})
    def __init__(self, *, gate: GatePort, b: BPort) -> None:
      pass

  @Adapter(BPort, key='first', lifecycle=SINGLETON)
  class B:
    def __init__(self, gate: GatePort, c: CPort) -> None:
      pass

  @Adapter(CPort, lifecycle=SINGLETON)
  class C:
    def __init__(self, gate: GatePort, a: APort | None = None) -> None:
      pass

  table = Wiring()
  table.mapper.register_batch(adapters=(Gate, A, B, C))
  racer = Racer(timeout=5)

  racer.run(
    lambda: table.resolve(APort),
    lambda: table.resolve(BPort, key='first'),
    lambda: table.resolve(CPort),
  )

  assert [type(error) for error in racer.errors] == [InjectionCycleError] * 3
  assert gate_built == []


@Port
class TallyPort(Protocol):
  pass


class Tally:
  """Mints a counted ``TRANSIENT`` adapter to put in front of a loop.
  The build makes it before it can discover the loop, so an empty tally proves the walk caught the
  cycle first. Without one, the build's own stack check raises before any constructor runs, and a
  walk that missed the cycle would look exactly like one that found it. It goes on the first
  adapter, ahead of the edge under test: a singleton deeper in runs its own walk on its own miss,
  which would catch the loop before a tally placed down there was ever built.
  """

  @staticmethod
  def adapter(built: list[str]) -> type[object]:
    """Return a fresh ``TallyPort`` adapter that records each construction in ``built``."""

    @Adapter(TallyPort)
    class Counted:
      def __init__(self) -> None:
        built.append('tally')

    return Counted


class TestCycleWalk:
  """The dry walk follows exactly the selections the build would make, and builds nothing."""

  def test_a_singleton_cycle_raises_before_any_constructor_runs(self) -> None:
    built: list[str] = []

    @Port
    class APort(Protocol):
      pass

    @Port
    class BPort(Protocol):
      pass

    @Adapter(APort, lifecycle=SINGLETON)
    class A:
      def __init__(self, tally: TallyPort, b: BPort) -> None:
        built.append('a')

    @Adapter(BPort, lifecycle=SINGLETON)
    class B:
      def __init__(self, a: APort) -> None:
        built.append('b')

    table = Wiring()
    table.mapper.register_batch(adapters=(Tally.adapter(built), A, B))

    with pytest.raises(InjectionCycleError) as cycle:
      table.resolve(APort)

    assert str(cycle.value).endswith(' -> '.join(map(QualifiedName.of, (A, B, A))))
    assert built == []

  def test_a_cycle_through_a_transient_middle_is_caught(self) -> None:
    built: list[str] = []

    @Port
    class FirstPort(Protocol):
      pass

    @Port
    class MiddlePort(Protocol):
      pass

    @Port
    class LastPort(Protocol):
      pass

    @Adapter(FirstPort, lifecycle=SINGLETON)
    class First:
      def __init__(self, middle: MiddlePort) -> None:
        pass

    @Adapter(MiddlePort)
    class Middle:
      def __init__(self, tally: TallyPort, last: LastPort) -> None:
        pass

    @Adapter(LastPort, lifecycle=SINGLETON)
    class Last:
      def __init__(self, first: FirstPort) -> None:
        pass

    table = Wiring()
    table.mapper.register_batch(adapters=(Tally.adapter(built), First, Middle, Last))

    with pytest.raises(InjectionCycleError) as cycle:
      table.resolve(FirstPort)

    expected = ' -> '.join(map(QualifiedName.of, (First, Middle, Last, First)))
    assert str(cycle.value).endswith(expected)
    assert built == []

  def test_the_walk_follows_the_keyed_adapter_not_the_unkeyed_one(self) -> None:
    built: list[str] = []

    @Port
    class EggPort(Protocol):
      pass

    @Port
    class HenPort(Protocol):
      pass

    @Adapter(EggPort, lifecycle=SINGLETON)
    class PlainEgg:
      pass

    @Adapter(EggPort, key='first', lifecycle=SINGLETON)
    class Egg:
      def __init__(self, hen: HenPort) -> None:
        pass

    @Adapter(HenPort, lifecycle=SINGLETON)
    class Hen:
      @Invert(keys={'egg': 'first'})
      def __init__(self, *, tally: TallyPort, egg: EggPort) -> None:
        pass

    table = Wiring()
    table.mapper.register_batch(adapters=(Tally.adapter(built), PlainEgg, Egg, Hen))

    with pytest.raises(InjectionCycleError) as cycle:
      table.resolve(HenPort)

    assert str(cycle.value).endswith(' -> '.join(map(QualifiedName.of, (Hen, Egg, Hen))))
    assert built == []

  def test_an_optional_edge_is_skipped_when_nothing_is_active_and_followed_when_something_is(
    self,
  ) -> None:
    built: list[str] = []

    @Port
    class ClockPort(Protocol):
      pass

    @Port
    class TowerPort(Protocol):
      pass

    @Adapter(TowerPort, lifecycle=SINGLETON)
    class Tower:
      def __init__(self, tally: TallyPort, clock: ClockPort | None) -> None:
        self.clock = clock

    @Adapter(ClockPort, envs={'prod'}, lifecycle=SINGLETON)
    class Clock:
      def __init__(self, tower: TowerPort) -> None:
        pass

    local, prod = Wiring('local'), Wiring('prod')
    tally = Tally.adapter(built)
    for table in (local, prod):
      table.mapper.register_batch(adapters=(tally, Tower, Clock))

    with pytest.raises(InjectionCycleError):
      prod.resolve(TowerPort)
    assert built == []
    assert local.resolve(TowerPort).clock is None

  def test_a_required_port_with_no_adapter_halts_the_walk_where_the_build_would_stop(
    self,
  ) -> None:
    # The cycle sits beyond a port nobody implements. The build raises AdapterNotFoundError before
    # it could ever reach the loop, so the walk must stop there too and not report the cycle.
    @Port
    class MissingPort(Protocol):
      pass

    @Port
    class SeedPort(Protocol):
      pass

    @Port
    class TreePort(Protocol):
      pass

    @Adapter(SeedPort, lifecycle=SINGLETON)
    class Seed:
      def __init__(self, missing: MissingPort, tree: TreePort) -> None:
        pass

    @Adapter(TreePort, lifecycle=SINGLETON)
    class Tree:
      def __init__(self, seed: SeedPort) -> None:
        pass

    table = Wiring()
    table.mapper.register_batch(adapters=(Seed, Tree))

    with pytest.raises(AdapterNotFoundError, match='MissingPort'):
      table.resolve(SeedPort)

  def test_an_acyclic_diamond_of_singletons_builds_each_once(self) -> None:
    built: list[str] = []

    @Port
    class RootPort(Protocol):
      pass

    @Port
    class LeftPort(Protocol):
      pass

    @Port
    class RightPort(Protocol):
      pass

    @Port
    class TopPort(Protocol):
      pass

    @Adapter(RootPort, lifecycle=SINGLETON)
    class Root:
      def __init__(self) -> None:
        built.append('root')

    @Adapter(LeftPort, lifecycle=SINGLETON)
    class Left:
      def __init__(self, root: RootPort) -> None:
        self.root = root

    @Adapter(RightPort, lifecycle=SINGLETON)
    class Right:
      def __init__(self, root: RootPort) -> None:
        self.root = root

    @Adapter(TopPort, lifecycle=SINGLETON)
    class Top:
      def __init__(self, left: LeftPort, right: RightPort) -> None:
        self.left = left
        self.right = right

    table = Wiring()
    table.mapper.register_batch(adapters=(Root, Left, Right, Top))

    top = table.resolve(TopPort)

    assert top.left.root is top.right.root
    assert built == ['root']

  def test_a_built_singleton_is_a_leaf_for_the_walk(self) -> None:
    # Like the build, the walk does not look inside a singleton it already has. The cached one here
    # was built before its dependency's adapter existed in this environment, so its plan now points
    # back up the graph; walking into it would report a loop the build can never take.
    @Port
    class LampPort(Protocol):
      pass

    @Port
    class WickPort(Protocol):
      pass

    @Adapter(WickPort, lifecycle=SINGLETON)
    class Wick:
      def __init__(self, lamp: LampPort | None = None) -> None:
        self.lamp = lamp

    @Adapter(LampPort, lifecycle=SINGLETON)
    class Lamp:
      def __init__(self, wick: WickPort) -> None:
        self.wick = wick

    table = Wiring()
    table.register_adapter(Wick)
    wick = table.resolve(WickPort)  # no Lamp registered yet, so its default is used
    table.register_adapter(Lamp)

    assert table.resolve(LampPort).wick is wick

  def test_the_walk_names_the_whole_path_from_the_first_adapter_built(self) -> None:
    # A TRANSIENT starts the build and the loop runs back to it through a singleton. The walk starts
    # from the build's stack, so it names the same path the construction-time check always has.
    @Port
    class FormPort(Protocol):
      pass

    @Port
    class StampPort(Protocol):
      pass

    @Adapter(FormPort)
    class Form:
      def __init__(self, stamp: StampPort) -> None:
        pass

    @Adapter(StampPort, lifecycle=SINGLETON)
    class Stamp:
      def __init__(self, form: FormPort) -> None:
        pass

    table = Wiring()
    table.mapper.register_batch(adapters=(Form, Stamp))

    with pytest.raises(InjectionCycleError) as cycle:
      table.resolve(FormPort)

    assert str(cycle.value).endswith(' -> '.join(map(QualifiedName.of, (Form, Stamp, Form))))


class TestConsumerBuiltInsideAConstructor:
  """U16: a consumer made inside a singleton's constructor continues that build's path.
  X's constructor builds an ``@Invert()`` consumer that needs Y, and Y takes X. No plan shows that
  edge, so before the build published its stack this was a ``RecursionError`` on one thread and a
  deadlock across two. Now the consumer starts from the published stack and the loop is ordinary.
  """

  def test_on_one_thread_the_loop_raises_a_cycle_error(self) -> None:
    @Port
    class XPort(Protocol):
      pass

    @Port
    class YPort(Protocol):
      pass

    class Consumer:
      @Invert()
      def __init__(self, *, y: YPort) -> None:
        pass

    @Adapter(XPort, lifecycle=SINGLETON)
    class X:
      def __init__(self) -> None:
        self.consumer = Consumer()

    @Adapter(YPort, lifecycle=SINGLETON)
    class Y:
      def __init__(self, x: XPort) -> None:
        pass

    Container.install(X, Y)

    with pytest.raises(InjectionCycleError) as cycle:
      Resolve.port(XPort)

    assert str(cycle.value).endswith(' -> '.join(map(QualifiedName.of, (X, Y, X))))
    assert Idunn()._resolver._building.current == ()  # restored on the way out of the failure

  def test_on_two_interleaved_threads_both_raise_instead_of_deadlocking(self) -> None:
    # Julia's probe. The first thread holds X's lock inside X's constructor; the second takes Y's
    # lock, builds Gate (which lets X go on) and queues for X. X's consumer then needs Y: before
    # the fix, each thread waited for the other's lock until the timeout.
    x_held, y_held = threading.Event(), threading.Event()

    @Port
    class GatePort(Protocol):
      pass

    @Port
    class XPort(Protocol):
      pass

    @Port
    class YPort(Protocol):
      pass

    @Adapter(GatePort)
    class Gate:
      def __init__(self) -> None:
        y_held.set()

    class Consumer:
      @Invert()
      def __init__(self, *, y: YPort) -> None:
        pass

    @Adapter(XPort, lifecycle=SINGLETON)
    class X:
      def __init__(self) -> None:
        x_held.set()
        y_held.wait(timeout=5)
        self.consumer = Consumer()

    @Adapter(YPort, lifecycle=SINGLETON)
    class Y:
      def __init__(self, gate: GatePort, x: XPort) -> None:
        pass

    Container.install(Gate, X, Y)
    racer = Racer(timeout=5)

    racer.run(lambda: Resolve.port(XPort), lambda: x_held.wait(5) and Resolve.port(YPort))

    assert [type(error) for error in racer.errors] == [InjectionCycleError, InjectionCycleError]
    assert sorted(str(error).rsplit(': ', 1)[1] for error in racer.errors) == [
      ' -> '.join(map(QualifiedName.of, (X, Y, X))),
      ' -> '.join(map(QualifiedName.of, (Y, X, Y))),
    ]
