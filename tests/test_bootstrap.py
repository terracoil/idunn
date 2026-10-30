"""``Idunn().bootstrap``: lazy, once-per-root autodiscovery for library entry points."""

import importlib
import shutil
from pathlib import Path
from textwrap import dedent
from threading import Barrier, Thread

import pytest
from idunn import Idunn, ReportMap


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
  def install(
    cls, *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, package: str, reenter: bool = False
  ) -> Path:
    """Write the package, put ``tmp_path`` on ``sys.path`` and return the package directory.

    With ``reenter`` the adapter module ends by bootstrapping its own root, as a library
    entry point running at import time would.
    """
    package_dir = tmp_path / package
    (package_dir / 'adapters').mkdir(parents=True)
    (package_dir / '__init__.py').write_text('', encoding='utf-8')
    (package_dir / 'adapters' / '__init__.py').write_text('', encoding='utf-8')
    (package_dir / 'ports.py').write_text(dedent(cls.PORTS).strip() + '\n', encoding='utf-8')
    adapter_source = dedent(cls.ADAPTER.format(package=package)).strip() + '\n'
    if reenter:
      adapter_source += dedent(cls.REENTRY.format(package=package))
    (package_dir / 'adapters' / 'apple.py').write_text(adapter_source, encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    return package_dir

  @staticmethod
  def take_apple(package: str) -> str:
    """Resolve the sample port through the singleton and pick an apple."""
    ports = importlib.import_module(f'{package}.ports')
    basket = Idunn()._inject(ports.AppleBasketPort)
    return str(basket.take_apple())


def test_bootstrap_discovers_and_wires_on_first_call(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  package = 'bootstrap_app_one'
  SamplePackage.install(tmp_path=tmp_path, monkeypatch=monkeypatch, package=package)

  report = Idunn().bootstrap(package)

  assert report['registered_adapters'] == (f'{package}.adapters.apple.GoldenAppleBasketAdapter',)
  assert SamplePackage.take_apple(package) == f'golden apple from {package}'


def test_bootstrap_returns_cached_report_without_rescanning(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  package = 'bootstrap_app_two'
  package_dir = SamplePackage.install(tmp_path=tmp_path, monkeypatch=monkeypatch, package=package)
  first = Idunn().bootstrap(package)

  # A real rescan would now find no modules on disk and produce an empty report.
  shutil.rmtree(package_dir / 'adapters')
  second = Idunn().bootstrap(package)

  assert second is first
  assert len(second['registered_adapters']) == 1


def test_bootstrap_ignores_options_on_repeat_calls(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  package = 'bootstrap_app_three'
  SamplePackage.install(tmp_path=tmp_path, monkeypatch=monkeypatch, package=package)
  first = Idunn().bootstrap(package)

  second = Idunn().bootstrap(package, adapter_package_names={'nowhere'}, strict=False)

  assert second is first
  assert len(second['registered_adapters']) == 1


def test_bootstrap_tracks_roots_independently(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  left, right = 'bootstrap_app_left', 'bootstrap_app_right'
  SamplePackage.install(tmp_path=tmp_path, monkeypatch=monkeypatch, package=left)
  SamplePackage.install(tmp_path=tmp_path, monkeypatch=monkeypatch, package=right)

  left_report = Idunn().bootstrap(left)
  right_report = Idunn().bootstrap(right)

  assert left_report is not right_report
  assert left_report['root_package'] == left
  assert right_report['root_package'] == right
  assert SamplePackage.take_apple(left) == f'golden apple from {left}'
  assert SamplePackage.take_apple(right) == f'golden apple from {right}'


def test_reset_forgets_bootstrap_so_it_rediscovers(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  package = 'bootstrap_app_four'
  SamplePackage.install(tmp_path=tmp_path, monkeypatch=monkeypatch, package=package)
  first = Idunn().bootstrap(package)

  second = Idunn().reset(environment='local').bootstrap(package)

  assert second is not first
  assert second == first
  assert SamplePackage.take_apple(package) == f'golden apple from {package}'


def test_bootstrap_is_safe_under_concurrent_first_calls(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  package = 'bootstrap_app_five'
  SamplePackage.install(tmp_path=tmp_path, monkeypatch=monkeypatch, package=package)
  thread_count = 8
  barrier = Barrier(thread_count)
  reports: list[ReportMap] = []

  def race() -> None:
    barrier.wait()
    reports.append(Idunn().bootstrap(package))

  threads = [Thread(target=race) for _ in range(thread_count)]
  for thread in threads:
    thread.start()
  for thread in threads:
    thread.join()

  assert len(reports) == thread_count
  assert all(report is reports[0] for report in reports)
  assert len(reports[0]['registered_adapters']) == 1


def test_bootstrap_reentered_during_discovery_does_not_deadlock(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  package = 'bootstrap_app_six'
  SamplePackage.install(tmp_path=tmp_path, monkeypatch=monkeypatch, package=package, reenter=True)
  reports: list[ReportMap] = []
  # Daemon thread: a regression to a plain Lock would hang forever, not fail the join.
  thread = Thread(target=lambda: reports.append(Idunn().bootstrap(package)), daemon=True)

  thread.start()
  thread.join(timeout=10)

  assert not thread.is_alive()
  # The nested call registers the adapter first and its report is the one kept.
  assert Idunn().bootstrap(package) is reports[0]
  assert len(reports[0]['registered_adapters']) == 1
  assert SamplePackage.take_apple(package) == f'golden apple from {package}'
