"""``Idunn().autodiscover``: every decorated class under the root, whatever its module is called."""

import importlib
import subprocess
import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from textwrap import dedent
from types import ModuleType

import pytest
from idunn import AdapterNotFoundError, DiscoveryError, Idunn, InvalidAdapterError

from _support import PackageWriter


class Sources:
  """Module sources shared by the discovery tests."""

  PORT = """
    from typing import Protocol
    from idunn import Port

    @Port
    class AppleBasketPort(Protocol):
      def take_apple(self) -> str: ...
  """
  BOOM = 'raise RuntimeError("this module must never be imported by discovery")'

  @staticmethod
  def adapter(
    package: str,
    *,
    port_module: str = 'ports',
    name: str = 'GoldenBasket',
    apple: str = 'golden',
  ) -> str:
    """Build an ``@Adapter`` for ``AppleBasketPort`` imported from ``<package>.<port_module>``."""
    return f"""
      from idunn import Adapter
      from {package}.{port_module} import AppleBasketPort

      @Adapter(AppleBasketPort)
      class {name}(AppleBasketPort):
        def take_apple(self) -> str:
          return "{apple}"
    """

  @staticmethod
  def both(*, name: str = 'GoldenBasket', apple: str = 'golden') -> str:
    """Build a module that declares a port and its adapter together."""
    return f"""
      from typing import Protocol
      from idunn import Adapter, Port

      @Port
      class AppleBasketPort(Protocol):
        def take_apple(self) -> str: ...

      @Adapter(AppleBasketPort)
      class {name}(AppleBasketPort):
        def take_apple(self) -> str:
          return "{apple}"
    """

  @staticmethod
  def take_apple(module_name: str) -> str:
    """Resolve ``AppleBasketPort`` from ``module_name`` through the singleton."""
    ports = importlib.import_module(module_name)
    return str(Idunn()._inject(ports.AppleBasketPort).take_apple())


@pytest.fixture
def writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PackageWriter:
  return PackageWriter(tmp_path=tmp_path, monkeypatch=monkeypatch)


def test_autodiscover_registers_decorated_classes_in_any_module(writer: PackageWriter) -> None:
  pkg = 'disc_any'
  writer.package(
    pkg,
    {
      'contracts.py': Sources.PORT,
      'impl/basket.py': Sources.adapter(pkg, port_module='contracts'),
    },
  )

  report = Idunn().autodiscover(pkg)

  assert report['imported_modules'] == (
    pkg,
    f'{pkg}.contracts',
    f'{pkg}.impl',
    f'{pkg}.impl.basket',
  )
  assert report['registered_ports'] == (f'{pkg}.contracts.AppleBasketPort',)
  assert report['registered_adapters'] == (f'{pkg}.impl.basket.GoldenBasket',)
  assert Sources.take_apple(f'{pkg}.contracts') == 'golden'


def test_autodiscover_registers_ports_before_adapters_across_modules(
  writer: PackageWriter,
) -> None:
  pkg = 'disc_order'
  writer.package(
    pkg,
    {
      'a_impl.py': Sources.adapter(pkg, port_module='z_contracts'),
      'z_contracts.py': Sources.PORT,
    },
  )

  report = Idunn().autodiscover(pkg)

  # register_adapter records the port implicitly; the port must still show up in the report.
  assert report['registered_ports'] == (f'{pkg}.z_contracts.AppleBasketPort',)
  assert report['registered_adapters'] == (f'{pkg}.a_impl.GoldenBasket',)


def test_autodiscover_handles_port_and_adapter_in_one_module(writer: PackageWriter) -> None:
  pkg = 'disc_onefile'
  writer.package(pkg, {'orchard.py': Sources.both()})

  report = Idunn().autodiscover(pkg)

  # The adapter subclasses its port but is not itself a port.
  assert report['registered_ports'] == (f'{pkg}.orchard.AppleBasketPort',)
  assert report['registered_adapters'] == (f'{pkg}.orchard.GoldenBasket',)
  assert Sources.take_apple(f'{pkg}.orchard') == 'golden'


def test_autodiscover_scans_the_root_package_init(writer: PackageWriter) -> None:
  pkg = 'disc_rootinit'
  writer.package(pkg, {'__init__.py': Sources.both()})

  report = Idunn().autodiscover(pkg)

  assert report['imported_modules'] == (pkg,)
  assert report['registered_ports'] == (f'{pkg}.AppleBasketPort',)
  assert report['registered_adapters'] == (f'{pkg}.GoldenBasket',)


def test_autodiscover_accepts_a_plain_module_root(writer: PackageWriter) -> None:
  writer.module('disc_plain', Sources.both())

  report = Idunn().autodiscover('disc_plain')

  assert report['imported_modules'] == ('disc_plain',)
  assert Sources.take_apple('disc_plain') == 'golden'


def test_autodiscover_walks_nested_and_namespace_packages(writer: PackageWriter) -> None:
  pkg = 'disc_nested'
  writer.package(
    pkg,
    {
      'a/b/c/contracts.py': Sources.PORT,
      # ``loose_ns`` gets no __init__.py: a PEP 420 namespace directory is still walked.
      'loose_ns/impl.py': Sources.adapter(pkg, port_module='a.b.c.contracts'),
    },
  )

  report = Idunn().autodiscover(pkg)

  assert f'{pkg}.loose_ns.impl' in report['imported_modules']
  assert report['registered_ports'] == (f'{pkg}.a.b.c.contracts.AppleBasketPort',)
  assert report['registered_adapters'] == (f'{pkg}.loose_ns.impl.GoldenBasket',)
  assert Sources.take_apple(f'{pkg}.a.b.c.contracts') == 'golden'


def test_autodiscover_never_imports_dunder_main(writer: PackageWriter) -> None:
  pkg = 'disc_main'
  writer.package(pkg, {'ports.py': Sources.PORT, '__main__.py': Sources.BOOM})

  report = Idunn().autodiscover(pkg)

  assert f'{pkg}.__main__' not in sys.modules
  assert report['imported_modules'] == (pkg, f'{pkg}.ports')


def test_autodiscover_skips_test_modules_by_default(writer: PackageWriter) -> None:
  pkg = 'disc_tests'
  writer.package(
    pkg,
    {
      'ports.py': Sources.PORT,
      'tests/__init__.py': Sources.BOOM,
      'tests/fakes.py': Sources.BOOM,
      'test/__init__.py': Sources.BOOM,
      'conftest.py': Sources.BOOM,
      'test_smoke.py': Sources.BOOM,
      'basket_test.py': Sources.BOOM,
    },
  )

  report = Idunn().autodiscover(pkg)

  assert report['imported_modules'] == (pkg, f'{pkg}.ports')


def test_autodiscover_exclude_adds_to_the_defaults(writer: PackageWriter) -> None:
  pkg = 'disc_extend'
  writer.package(
    pkg,
    {
      'ports.py': Sources.PORT,
      'migrations/__init__.py': Sources.BOOM,
      'tests/fakes.py': Sources.BOOM,
    },
  )

  report = Idunn().autodiscover(pkg, exclude={'migrations'})

  # Naming an extra exclusion must not switch the test-module defaults back on.
  assert report['imported_modules'] == (pkg, f'{pkg}.ports')


def test_autodiscover_exclude_accepts_a_single_string(writer: PackageWriter) -> None:
  pkg = 'disc_string'
  writer.package(pkg, {'ports.py': Sources.PORT, 'scripts/seed.py': Sources.BOOM})

  report = Idunn().autodiscover(pkg, exclude='scripts')

  assert report['imported_modules'] == (pkg, f'{pkg}.ports')


def test_autodiscover_exclude_prunes_a_whole_subtree(writer: PackageWriter) -> None:
  pkg = 'disc_prune'
  writer.package(
    pkg,
    {
      'ports.py': Sources.PORT,
      'analytics/__init__.py': Sources.BOOM,
      'analytics/reports.py': Sources.BOOM,
    },
  )

  Idunn().autodiscover(pkg, exclude='analytics')

  assert f'{pkg}.analytics' not in sys.modules
  assert f'{pkg}.analytics.reports' not in sys.modules


def test_autodiscover_matches_exclusions_below_the_root_only(writer: PackageWriter) -> None:
  pkg = 'disc_fakes_root'
  writer.package(pkg, {'tests/fakes.py': Sources.both(name='FakeBasket', apple='fake')})

  # A test package named as the root is scanned on purpose: its own name never matches.
  report = Idunn().autodiscover(f'{pkg}.tests')

  assert report['registered_adapters'] == (f'{pkg}.tests.fakes.FakeBasket',)
  assert Sources.take_apple(f'{pkg}.tests.fakes') == 'fake'


def test_autodiscover_skips_paths_that_are_not_identifiers(writer: PackageWriter) -> None:
  pkg = 'disc_ident'
  writer.package(
    pkg,
    {
      'ports.py': Sources.PORT,
      'my-scripts/run.py': Sources.BOOM,
      '0001_initial.py': Sources.BOOM,
    },
  )

  report = Idunn().autodiscover(pkg, strict=True)

  assert report['imported_modules'] == (pkg, f'{pkg}.ports')


def test_autodiscover_registers_a_reexported_class_once(writer: PackageWriter) -> None:
  pkg = 'disc_reexport'
  writer.package(
    pkg,
    {
      'ports.py': Sources.PORT,
      '_impl.py': Sources.adapter(pkg),
      '__init__.py': 'from ._impl import GoldenBasket\n\nAlias = GoldenBasket',
    },
  )

  report = Idunn().autodiscover(pkg)

  # Private modules are scanned; the class is attributed to the module that defines it.
  assert report['registered_adapters'] == (f'{pkg}._impl.GoldenBasket',)
  assert Sources.take_apple(f'{pkg}.ports') == 'golden'


def test_autodiscover_ignores_classes_imported_from_outside_the_root(
  writer: PackageWriter,
) -> None:
  writer.package('disc_lib', {'ports.py': Sources.PORT, 'adapters.py': Sources.adapter('disc_lib')})
  writer.package('disc_app', {'service.py': 'from disc_lib.adapters import GoldenBasket'})

  report = Idunn().autodiscover('disc_app')

  assert report['registered_ports'] == ()
  assert report['registered_adapters'] == ()


def test_autodiscover_keeps_excluded_classes_out_even_when_imported(
  writer: PackageWriter,
) -> None:
  pkg = 'disc_excluded_import'
  writer.package(
    pkg,
    {
      'ports.py': Sources.PORT,
      'tests/fakes.py': Sources.adapter(pkg, name='FakeBasket', apple='fake'),
      'service.py': f'from {pkg}.tests.fakes import FakeBasket',
    },
  )

  report = Idunn().autodiscover(pkg)

  assert report['registered_adapters'] == ()
  with pytest.raises(AdapterNotFoundError):
    Sources.take_apple(f'{pkg}.ports')


def test_autodiscover_ignores_undecorated_subclasses(writer: PackageWriter) -> None:
  pkg = 'disc_subclass'
  writer.package(
    pkg,
    {
      'ports.py': Sources.PORT,
      'adapters.py': f"""
        from idunn import Adapter
        from {pkg}.ports import AppleBasketPort

        @Adapter(AppleBasketPort)
        class GoldenBasket(AppleBasketPort):
          def take_apple(self) -> str:
            return "golden"

        class TartBasket(GoldenBasket):
          pass
      """,
    },
  )

  report = Idunn().autodiscover(pkg)

  assert report['registered_adapters'] == (f'{pkg}.adapters.GoldenBasket',)


def test_autodiscover_does_not_register_undecorated_classes(writer: PackageWriter) -> None:
  pkg = 'disc_undecorated'
  writer.package(
    pkg,
    {
      'ports.py': Sources.PORT,
      'adapters.py': f"""
        from {pkg}.ports import AppleBasketPort

        class PlainBasket(AppleBasketPort):
          def take_apple(self) -> str:
            return "plain"
      """,
    },
  )

  report = Idunn().autodiscover(pkg)

  assert report['registered_adapters'] == ()
  with pytest.raises(AdapterNotFoundError):
    Sources.take_apple(f'{pkg}.ports')


def test_autodiscover_strict_raises_before_registering_anything(writer: PackageWriter) -> None:
  pkg = 'disc_strict'
  writer.package(pkg, {'ports.py': Sources.PORT, 'zz_broken.py': Sources.BOOM})

  with pytest.raises(DiscoveryError, match='zz_broken'):
    Idunn().autodiscover(pkg)

  # Everything imports before anything registers, so a failure leaves the catalog untouched.
  assert Idunn()._mapper.ports == frozenset()


def test_autodiscover_collision_registers_nothing_from_the_run(writer: PackageWriter) -> None:
  pkg = 'disc_collision'
  writer.package(
    pkg,
    {
      'ports.py': Sources.PORT,
      'a_golden.py': Sources.adapter(pkg),
      'b_rival.py': Sources.adapter(pkg, name='RivalBasket', apple='rival'),
    },
  )

  with pytest.raises(InvalidAdapterError, match=f'{pkg}.a_golden.GoldenBasket and .*RivalBasket'):
    Idunn().autodiscover(pkg)

  # One batch, validated whole: the port and the first module's adapter never registered either.
  assert Idunn()._mapper.ports == frozenset()
  assert Idunn().describe() == 'Environment: local'


@pytest.mark.parametrize('strict', [True, False])
def test_autodiscover_refuses_a_zipped_root_whatever_strict_says(
  writer: PackageWriter, strict: bool
) -> None:
  pkg = f'disc_zipped_{str(strict).lower()}'
  archive = writer.zipped_package(pkg, {'__init__.py': Sources.PORT, 'adapters.py': Sources.both()})

  with pytest.raises(DiscoveryError, match=f'{pkg}.*{archive.name}'):
    Idunn().autodiscover(pkg, strict=strict)

  # Refused before scanning: nothing below the root is imported, and not even its port registers.
  assert f'{pkg}.adapters' not in sys.modules
  assert Idunn()._mapper.ports == frozenset()


def test_autodiscover_non_strict_skips_and_reports_unimportable(writer: PackageWriter) -> None:
  pkg = 'disc_lenient'
  writer.package(
    pkg,
    {'ports.py': Sources.PORT, 'adapters.py': Sources.adapter(pkg), 'broken.py': Sources.BOOM},
  )

  report = Idunn().autodiscover(pkg, strict=False)

  assert report['skipped_modules'] == (f'{pkg}.broken',)
  assert report['registered_adapters'] == (f'{pkg}.adapters.GoldenBasket',)
  assert Sources.take_apple(f'{pkg}.ports') == 'golden'


def test_autodiscover_constructs_nothing(writer: PackageWriter) -> None:
  pkg = 'disc_lazy'
  writer.package(
    pkg,
    {
      'ports.py': """
        from typing import Protocol
        from idunn import Port

        @Port
        class AppleBasketPort(Protocol):
          def take_apple(self) -> str: ...

        @Port
        class FeastPort(Protocol):
          def serve(self) -> str: ...
      """,
      'feast.py': f"""
        from idunn import Adapter
        from {pkg}.ports import AppleBasketPort, FeastPort

        constructed = 0

        @Adapter(FeastPort)
        class FeastAdapter(FeastPort):
          def __init__(self, basket: AppleBasketPort) -> None:
            global constructed
            constructed += 1
            self._basket = basket

          def serve(self) -> str:
            return f"feast with {{self._basket.take_apple()}}"
      """,
      'z_apple.py': f"""
        from idunn import Adapter
        from {pkg}.ports import AppleBasketPort

        constructed = 0

        @Adapter(AppleBasketPort)
        class GoldenBasket(AppleBasketPort):
          def __init__(self) -> None:
            global constructed
            constructed += 1

          def take_apple(self) -> str:
            return "golden"
      """,
    },
  )

  report = Idunn().autodiscover(pkg)
  ports = importlib.import_module(f'{pkg}.ports')
  feast_module = importlib.import_module(f'{pkg}.feast')
  apple_module = importlib.import_module(f'{pkg}.z_apple')

  assert feast_module.constructed == 0
  assert apple_module.constructed == 0
  assert report['registered_adapters'] == (
    f'{pkg}.feast.FeastAdapter',
    f'{pkg}.z_apple.GoldenBasket',
  )

  feast = Idunn()._inject(ports.FeastPort)

  assert feast.serve() == 'feast with golden'
  assert feast_module.constructed == 1
  assert apple_module.constructed == 1


def test_autodiscover_registers_ports_without_adapters(writer: PackageWriter) -> None:
  pkg = 'disc_ports_only'
  writer.package(pkg, {'ports.py': Sources.PORT})

  report = Idunn().autodiscover(pkg)

  assert report['imported_modules'] == (pkg, f'{pkg}.ports')
  assert report['registered_ports'] == (f'{pkg}.ports.AppleBasketPort',)
  assert report['registered_adapters'] == ()


def test_autodiscover_registers_conventional_layout(writer: PackageWriter) -> None:
  pkg = 'disc_conventional'
  writer.package(pkg, {'ports.py': Sources.PORT, 'adapters/apple.py': Sources.adapter(pkg)})

  report = Idunn().autodiscover(pkg)

  assert report['imported_modules'] == (
    pkg,
    f'{pkg}.adapters',
    f'{pkg}.adapters.apple',
    f'{pkg}.ports',
  )
  assert report['registered_ports'] == (f'{pkg}.ports.AppleBasketPort',)
  assert report['registered_adapters'] == (f'{pkg}.adapters.apple.GoldenBasket',)
  assert Sources.take_apple(f'{pkg}.ports') == 'golden'


def test_autodiscover_is_idempotent_on_repeat(writer: PackageWriter) -> None:
  pkg = 'disc_repeat'
  writer.package(pkg, {'ports.py': Sources.PORT, 'adapters.py': Sources.adapter(pkg)})

  first = Idunn().autodiscover(pkg)
  second = Idunn().autodiscover(pkg)

  assert second['imported_modules'] == first['imported_modules']
  assert second['registered_ports'] == ()
  assert second['registered_adapters'] == ()


def test_autodiscover_scans_the_running_main_instead_of_importing_it(
  writer: PackageWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
  pkg = 'disc_running'
  writer.package(pkg, {'cli.py': Sources.BOOM})
  # Stand in for ``python -m disc_running.cli``: a ``__main__`` whose spec names that module.
  running = ModuleType('__main__')
  running.__spec__ = ModuleSpec(f'{pkg}.cli', loader=None)
  exec(dedent(Sources.both()), running.__dict__)
  monkeypatch.setitem(sys.modules, '__main__', running)

  report = Idunn().autodiscover(pkg)

  assert f'{pkg}.cli' not in sys.modules
  # Names sort before import, so the running module sits in its dotted name's slot.
  assert report['imported_modules'] == (pkg, '__main__')
  assert report['registered_adapters'] == ('__main__.GoldenBasket',)


def test_autodiscover_reuses_the_module_running_as_main(tmp_path: Path) -> None:
  pkg = 'disc_run'
  package_dir = tmp_path / pkg
  package_dir.mkdir()
  (package_dir / '__init__.py').write_text('', encoding='utf-8')
  (package_dir / 'main.py').write_text(
    dedent(
      f"""
      from typing import Protocol
      from idunn import Adapter, Idunn, Invert, Port

      @Port
      class AppleBasketPort(Protocol):
        def take_apple(self) -> str: ...

      @Adapter(AppleBasketPort)
      class GoldenBasket(AppleBasketPort):
        def take_apple(self) -> str:
          return "golden"

      class Feast:
        basket: AppleBasketPort

        @Invert()
        def __init__(self, basket: AppleBasketPort) -> None:
          pass

      if __name__ == "__main__":
        Idunn().autodiscover("{pkg}")
        print(Feast().basket.take_apple())
      """
    ).strip()
    + '\n',
    encoding='utf-8',
  )

  # Importing main.py a second time would register a different AppleBasketPort than the one
  # the running Feast asks for, and the print would fail with AdapterNotFoundError.
  result = subprocess.run(
    [sys.executable, '-m', f'{pkg}.main'],
    cwd=tmp_path,
    capture_output=True,
    text=True,
    check=False,
  )

  assert result.returncode == 0, result.stderr
  assert result.stdout.strip() == 'golden'


def test_examples_my_app_follows_the_recommended_layout() -> None:
  report = Idunn().autodiscover('examples.my_app')

  assert report['registered_ports'] == ('examples.my_app.ports.AppleBasketPort',)
  assert report['registered_adapters'] == ('examples.my_app.adapters.GoldenAppleBasketAdapter',)
