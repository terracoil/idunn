"""``Idunn().bootstrap``: lazy, once-per-root autodiscovery for library entry points."""

import importlib
import inspect
import json
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from idunn import DiscoveryError, Idunn, ReportMap

from _support import PackageWriter, Racer, Resolve

REPO_ROOT = Path(__file__).resolve().parent.parent


class SamplePackage:
  """Writes a tiny discoverable package (one port, one adapter) under ``tmp_path``."""

  PORTS = """
    from typing import Protocol
    from idunn import Port

    @Port
    class AppleBasketPort(Protocol):
        def take_apple(self) -> str: ...
  """
  ADAPTER = """
    from idunn import Adapter
    from {package}.ports import AppleBasketPort

    @Adapter(AppleBasketPort)
    class GoldenAppleBasketAdapter(AppleBasketPort):
        def take_apple(self) -> str:
            return "golden apple from {package}"
  """
  REENTRY = """
    from idunn import Idunn

    Idunn().bootstrap("{package}")
  """

  @classmethod
  def install(cls, writer: PackageWriter, *, package: str, reenter: bool = False) -> Path:
    """Write the package through ``writer`` and return its directory.
    With ``reenter`` the adapter module ends by bootstrapping its own root, as a library entry
    point running at import time would.
    """
    adapter: str = dedent(cls.ADAPTER.format(package=package)).strip()
    reentry: str = dedent(cls.REENTRY.format(package=package)).strip() if reenter else ''
    return writer.package(
      package, {'ports.py': cls.PORTS, 'adapters/apple.py': f'{adapter}\n\n{reentry}'}
    )

  @staticmethod
  def take_apple(package: str) -> str:
    """Resolve the sample port through the singleton and pick an apple."""
    ports = importlib.import_module(f'{package}.ports')
    basket = Resolve.port(ports.AppleBasketPort)
    return str(basket.take_apple())


def test_bootstrap_discovers_and_wires_on_first_call(writer: PackageWriter) -> None:
  package = 'bootstrap_app_one'
  SamplePackage.install(writer, package=package)

  report = Idunn().bootstrap(package)

  assert report['registered_adapters'] == (f'{package}.adapters.apple.GoldenAppleBasketAdapter',)
  assert SamplePackage.take_apple(package) == f'golden apple from {package}'


def test_bootstrap_returns_cached_report_without_rescanning(writer: PackageWriter) -> None:
  package = 'bootstrap_app_two'
  package_dir = SamplePackage.install(writer, package=package)
  first = Idunn().bootstrap(package)

  # A rescan could not list the deleted adapters, so the identical object proves none happened.
  shutil.rmtree(package_dir / 'adapters')
  second = Idunn().bootstrap(package)

  assert second is first
  assert len(second['registered_adapters']) == 1


def test_bootstrap_ignores_options_on_repeat_calls(writer: PackageWriter) -> None:
  package = 'bootstrap_app_three'
  SamplePackage.install(writer, package=package)
  first = Idunn().bootstrap(package)

  second = Idunn().bootstrap(package, exclude='adapters', strict=False)

  assert second is first
  assert len(second['registered_adapters']) == 1


def test_bootstrap_tracks_roots_independently(writer: PackageWriter) -> None:
  left, right = 'bootstrap_app_left', 'bootstrap_app_right'
  SamplePackage.install(writer, package=left)
  SamplePackage.install(writer, package=right)

  left_report = Idunn().bootstrap(left)
  right_report = Idunn().bootstrap(right)

  assert left_report is not right_report
  assert left_report['root_package'] == left
  assert right_report['root_package'] == right
  assert SamplePackage.take_apple(left) == f'golden apple from {left}'
  assert SamplePackage.take_apple(right) == f'golden apple from {right}'


def test_reset_forgets_bootstrap_so_it_rediscovers(writer: PackageWriter) -> None:
  package = 'bootstrap_app_four'
  SamplePackage.install(writer, package=package)
  first = Idunn().bootstrap(package)

  second = Idunn().reset(environment='local').bootstrap(package)

  assert second is not first
  assert second == first
  assert SamplePackage.take_apple(package) == f'golden apple from {package}'


def test_bootstrap_is_safe_under_concurrent_first_calls(writer: PackageWriter) -> None:
  package = 'bootstrap_app_five'
  SamplePackage.install(writer, package=package)
  thread_count = 8
  reports: list[ReportMap] = []
  racer = Racer(timeout=10)

  racer.run(*(lambda: reports.append(Idunn().bootstrap(package)) for _ in range(thread_count)))

  assert racer.errors == []
  assert len(reports) == thread_count
  assert all(report is reports[0] for report in reports)
  assert len(reports[0]['registered_adapters']) == 1


def test_bootstrap_reentered_during_discovery_does_not_deadlock(writer: PackageWriter) -> None:
  package = 'bootstrap_app_six'
  SamplePackage.install(writer, package=package, reenter=True)
  # On a Racer thread: a regression to a plain Lock would hang forever, not fail the call.
  report: ReportMap = Racer(timeout=10).call(lambda: Idunn().bootstrap(package))

  # The nested run registers the adapter, the outer run finds nothing new, and the outer call,
  # last out, caches the merge of both and returns it.
  assert Idunn().bootstrap(package) is report
  assert len(report['registered_adapters']) == 1
  assert SamplePackage.take_apple(package) == f'golden apple from {package}'


class MergeSources:
  """Packages whose modules call ``bootstrap`` for their own root while they are being imported."""

  PORTS = """
    from typing import Protocol
    from idunn import Port

    @Port
    class AppleBasketPort(Protocol):
        def take_apple(self) -> str: ...

    @Port
    class PearBasketPort(Protocol):
        def take_pear(self) -> str: ...
  """
  # One adapter before the nested call and one after: 1.x cached the nested report and lost Second.
  MIDDLE = """
    from idunn import Adapter, Idunn
    from {package}.ports import AppleBasketPort, PearBasketPort

    @Adapter(AppleBasketPort)
    class First(AppleBasketPort):
        def take_apple(self) -> str:
            return "first"

    NESTED = Idunn().bootstrap("{package}")

    @Adapter(PearBasketPort)
    class Second(PearBasketPort):
        def take_pear(self) -> str:
            return "second"
  """
  # The call comes before anything is defined, which 1.x documented as "put it at the end instead".
  TOP = """
    from idunn import Idunn

    NESTED = Idunn().bootstrap("{package}")

    from idunn import Adapter
    from {package}.ports import AppleBasketPort

    @Adapter(AppleBasketPort)
    class Late(AppleBasketPort):
        def take_apple(self) -> str:
            return "late"
  """


def test_reentrant_bootstrap_caches_classes_defined_after_the_nested_call(
  writer: PackageWriter,
) -> None:
  package = 'bootstrap_merge_middle'
  writer.package(
    package,
    {
      'ports.py': MergeSources.PORTS,
      'adapters.py': MergeSources.MIDDLE.format(package=package),
    },
  )

  report = Idunn().bootstrap(package)

  nested: ReportMap = importlib.import_module(f'{package}.adapters').NESTED
  assert nested['registered_adapters'] == (f'{package}.adapters.First',)
  assert report['registered_adapters'] == (
    f'{package}.adapters.First',
    f'{package}.adapters.Second',
  )
  assert report['registered_ports'] == (
    f'{package}.ports.AppleBasketPort',
    f'{package}.ports.PearBasketPort',
  )
  assert Idunn().bootstrap(package) is report


def test_bootstrap_at_the_top_of_a_module_still_caches_every_class(writer: PackageWriter) -> None:
  package = 'bootstrap_merge_top'
  writer.package(
    package,
    {
      'ports.py': MergeSources.PORTS,
      'adapters.py': MergeSources.TOP.format(package=package),
    },
  )

  report = Idunn().bootstrap(package)

  # The nested run saw an empty adapters module; only the outer run could register Late.
  nested: ReportMap = importlib.import_module(f'{package}.adapters').NESTED
  assert nested['registered_adapters'] == ()
  assert report['registered_adapters'] == (f'{package}.adapters.Late',)
  assert len(report['registered_ports']) == 2
  assert Idunn().bootstrap(package) is report


def test_import_time_bootstrap_from_a_module_outside_the_root(writer: PackageWriter) -> None:
  package = 'bootstrap_app_eight'
  SamplePackage.install(writer, package=package)
  writer.module(
    'bootstrap_outside_caller',
    f"""
    from idunn import Idunn

    REPORT = Idunn().bootstrap("{package}")
    """,
  )

  caller = importlib.import_module('bootstrap_outside_caller')

  # Mid-import with no flight to join, it is simply the owner: it discovers and caches.
  assert caller.REPORT['registered_adapters'] == (
    f'{package}.adapters.apple.GoldenAppleBasketAdapter',
  )
  assert Idunn().bootstrap(package) is caller.REPORT
  assert SamplePackage.take_apple(package) == f'golden apple from {package}'


def test_autodiscover_and_bootstrap_share_one_signature() -> None:
  assert inspect.signature(Idunn.autodiscover) == inspect.signature(Idunn.bootstrap)


def test_bootstrap_retries_after_a_failed_discovery(writer: PackageWriter) -> None:
  package = 'bootstrap_app_seven'
  package_dir = SamplePackage.install(writer, package=package)
  broken = package_dir / 'broken.py'
  broken.write_text('raise RuntimeError("not yet")\n', encoding='utf-8')

  with pytest.raises(DiscoveryError, match='broken'):
    Idunn().bootstrap(package)

  # A failed run is not cached, so fixing the module and calling again discovers for real.
  broken.unlink()
  importlib.invalidate_caches()
  report = Idunn().bootstrap(package)

  assert len(report['registered_adapters']) == 1
  assert SamplePackage.take_apple(package) == f'golden apple from {package}'


class DeadlockScenario:
  """The 1.x import-time deadlock, staged in files for a child interpreter to act out.
  Thread A bootstraps ``dl_pkg`` and is parked inside ``dl_pkg.a``'s body. Thread B imports
  ``dl_pkg.n``, whose first act is to call ``bootstrap``. In 1.x, B queued on the bootstrap lock A
  held while A queued on ``dl_pkg.n``'s import lock B held, and neither ever moved again. Because
  ``n`` bootstraps at its top, its own classes reach the cache only through A's run: the cached
  report lists them only if every run is merged.
  """

  SYNC = """
    import threading

    a_started = threading.Event()
    n_entered = threading.Event()
    reports = {}
  """
  A = """
    from typing import Protocol

    import dl_sync
    from idunn import Adapter, Port

    @Port
    class APort(Protocol):
        def ping(self) -> str: ...

    @Adapter(APort)
    class AAdapter(APort):
        def ping(self) -> str:
            return "a"

    dl_sync.a_started.set()
    dl_sync.n_entered.wait(5)
  """
  N = """
    from typing import Protocol

    import dl_sync
    from idunn import Adapter, Idunn, Port

    dl_sync.n_entered.set()
    dl_sync.reports["participant"] = Idunn().bootstrap("dl_pkg")

    @Port
    class NPort(Protocol):
        def ping(self) -> str: ...

    @Adapter(NPort)
    class NAdapter(NPort):
        def ping(self) -> str:
            return "n"
  """
  DRIVER = """
    import json
    import os
    import sys
    import threading

    sys.path[:0] = [sys.argv[1], sys.argv[2]]

    import dl_sync
    from idunn import Idunn

    errors = []

    def guarded(target):
        def run():
            try:
                target()
            except BaseException as error:
                errors.append(repr(error))
        return run

    def own():
        dl_sync.reports["owner"] = Idunn().bootstrap("dl_pkg")

    def importer():
        dl_sync.a_started.wait(5)
        import dl_pkg.n

    threads = [
        threading.Thread(target=guarded(own), daemon=True),
        threading.Thread(target=guarded(importer), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    alive = [thread.is_alive() for thread in threads]
    payload = {"alive": alive, "errors": errors}
    if not any(alive) and not errors:
        cached = Idunn().bootstrap("dl_pkg")
        payload["cached_adapters"] = list(cached["registered_adapters"])
        payload["participant_adapters"] = list(
            dl_sync.reports["participant"]["registered_adapters"]
        )
        payload["owner_is_cached"] = dl_sync.reports["owner"] is cached
    print(json.dumps(payload), flush=True)
    os._exit(1 if any(alive) else 0)
  """

  @classmethod
  def write(cls, writer: PackageWriter) -> None:
    """Write the sync module, the package and the driver where the child will find them."""
    writer.module('dl_sync', cls.SYNC)
    writer.module('dl_driver', cls.DRIVER)
    writer.package('dl_pkg', {'a.py': cls.A, 'n.py': cls.N})


def test_import_time_bootstrap_does_not_deadlock_against_concurrent_discovery(
  tmp_path: Path, writer: PackageWriter
) -> None:
  DeadlockScenario.write(writer)

  # A child process, so a regression fails this test instead of leaving a daemon thread holding a
  # lock that hangs every later bootstrap in the suite.
  result = subprocess.run(
    [sys.executable, str(tmp_path / 'dl_driver.py'), str(tmp_path), str(REPO_ROOT)],
    capture_output=True,
    text=True,
    timeout=30,
    check=False,
  )

  assert result.returncode == 0, result.stdout + result.stderr
  payload = json.loads(result.stdout)
  assert payload['alive'] == [False, False]
  assert payload['errors'] == []
  assert payload['owner_is_cached'] is True
  # B could not wait for A, so it ran its own discovery and got its own report: n was still empty.
  assert payload['participant_adapters'] == ['dl_pkg.a.AAdapter']
  assert payload['cached_adapters'] == ['dl_pkg.a.AAdapter', 'dl_pkg.n.NAdapter']


class CrossRootScenario:
  """Two roots whose modules bootstrap each other at import time, from two threads, plus a waiter.
  ``xr_one.x`` calls ``bootstrap('xr_two')`` and ``xr_two.y`` calls ``bootstrap('xr_one')``, each
  after a handshake, so both threads end up importing the module the other holds. Nobody waits on
  Idunn, so the cycle is between module locks alone, and importlib breaks it the way it breaks any
  concurrent circular import: one import fails. That surfaces as one ``DiscoveryError``, and its
  root's owner fails after an import-time participant already registered everything; the retry
  finds nothing new, so the cached report is complete only if the participant's run carries over.
  """

  SYNC = """
    import threading

    x_in = threading.Event()
    y_in = threading.Event()
  """
  MODULE = """
    from typing import Protocol

    import xr_sync
    from idunn import Adapter, Idunn, Port

    @Port
    class {name}Port(Protocol):
        def ping(self) -> str: ...

    @Adapter({name}Port)
    class {name}Adapter({name}Port):
        def ping(self) -> str:
            return "{name}"

    xr_sync.{mine}_in.set()
    xr_sync.{theirs}_in.wait(5)
    Idunn().bootstrap("{other_root}")

    @Adapter({name}Port, key="late")
    class {name}Late({name}Port):
        def ping(self) -> str:
            return "late"
  """
  DRIVER = """
    import json
    import os
    import sys
    import threading

    sys.path[:0] = [sys.argv[1], sys.argv[2]]

    import xr_sync
    from idunn import Idunn

    errors = []
    results = {}

    def guarded(name, target):
        def run():
            try:
                results[name] = target()
            except BaseException as error:
                errors.append(repr(error))
        return run

    def wait_then_call():
        xr_sync.x_in.wait(5)
        xr_sync.y_in.wait(5)
        return Idunn().bootstrap("xr_one")

    threads = [
        threading.Thread(target=guarded("one", lambda: Idunn().bootstrap("xr_one")), daemon=True),
        threading.Thread(target=guarded("two", lambda: Idunn().bootstrap("xr_two")), daemon=True),
        threading.Thread(target=guarded("waiter", wait_then_call), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    alive = [thread.is_alive() for thread in threads]
    payload = {"alive": alive, "errors": errors}
    if not any(alive):
        one, two = Idunn().bootstrap("xr_one"), Idunn().bootstrap("xr_two")
        payload["one"] = sorted(one["registered_adapters"])
        payload["two"] = sorted(two["registered_adapters"])
        payload["waiter_is_cached"] = results.get("waiter") is one
    print(json.dumps(payload), flush=True)
    os._exit(1 if any(alive) else 0)
  """

  @classmethod
  def write(cls, writer: PackageWriter) -> None:
    """Write the sync module, both roots and the driver where the child will find them."""
    writer.module('xr_sync', cls.SYNC)
    writer.module('xr_driver', cls.DRIVER)
    one = cls.MODULE.format(name='X', mine='x', theirs='y', other_root='xr_two')
    two = cls.MODULE.format(name='Y', mine='y', theirs='x', other_root='xr_one')
    writer.package('xr_one', {'x.py': one})
    writer.package('xr_two', {'y.py': two})


def test_roots_bootstrapping_each_other_at_import_time_cache_complete_reports(
  tmp_path: Path, writer: PackageWriter
) -> None:
  CrossRootScenario.write(writer)

  result = subprocess.run(
    [sys.executable, str(tmp_path / 'xr_driver.py'), str(tmp_path), str(REPO_ROOT)],
    capture_output=True,
    text=True,
    timeout=30,
    check=False,
  )

  assert result.returncode == 0, result.stdout + result.stderr
  payload = json.loads(result.stdout)
  assert payload['alive'] == [False, False, False]
  # importlib's tie-break: exactly one entry-point call loses, as with any circular import race.
  assert len(payload['errors']) == 1
  assert payload['errors'][0].startswith('DiscoveryError(')
  assert payload['waiter_is_cached'] is True
  assert payload['one'] == ['xr_one.x.XAdapter', 'xr_one.x.XLate']
  assert payload['two'] == ['xr_two.y.YAdapter', 'xr_two.y.YLate']
