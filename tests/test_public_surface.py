"""The public surface lives in two barrels, and tests and examples import it from there.
Top-level ``idunn`` holds what applications use; ``idunn.testing`` holds what their tests use, kept
apart so production code never has a reason to import it. Everything else comes from its layer
package (``idunn.domain``, ``idunn.internal``, ``idunn.util``), never from a module path, so files
can move without a scavenger hunt.
"""

import ast
from collections.abc import Mapping
from pathlib import Path

import idunn
import idunn.testing

REPO_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_PUBLIC_NAMES = {
  'Adapter',
  'AdapterNotFoundError',
  'DiscoveryError',
  'Idunn',
  'IdunnError',
  'InjectionCycleError',
  'InvalidAdapterError',
  'InvalidPortError',
  'Invert',
  'LifecycleEnum',
  'MissingTypeHintError',
  'Port',
  'ReportMap',
}

EXPECTED_TESTING_NAMES = {'Harness'}


class ImportProbe:
  """Finds absolute imports that bypass a public barrel or reach past a layer package.
  ``from idunn... import`` is flagged for a module path, or for a public name imported from
  anywhere but its home barrel (``Harness`` from ``idunn.app``, or ``Port`` from
  ``idunn.testing``), and plain ``import idunn.x.y`` for the module path. ``import idunn.internal``
  names a layer package, which is allowed, so the same two-dot line applies to both forms.
  """

  ROOTS: tuple[Path, ...] = (REPO_ROOT / 'tests', REPO_ROOT / 'examples')

  @staticmethod
  def homes() -> dict[str, str]:
    """Map every public name to the one barrel it may be imported from."""
    return {name: 'idunn' for name in idunn.__all__} | {
      name: 'idunn.testing' for name in idunn.testing.__all__
    }

  @staticmethod
  def offenders(path: Path, homes: Mapping[str, str]) -> list[str]:
    """Return ``line dotted.name`` for each misplaced public name or module path from ``idunn``.
    Relative imports (``level > 0``) and bare ``from . import x`` (``module is None``) are
    skipped: they never name the ``idunn`` package. Hits are ordered by line number, because
    ``ast.walk`` is breadth-first.
    """
    tree: ast.Module = ast.parse(path.read_text(encoding='utf-8'))
    from_hits: list[tuple[int, str]] = [
      (node.lineno, f'{node.lineno} {node.module}.{alias.name}')
      for node in ast.walk(tree)
      if isinstance(node, ast.ImportFrom)
      and node.level == 0
      and node.module is not None
      and (node.module == 'idunn' or node.module.startswith('idunn.'))
      for alias in node.names
      if node.module.count('.') > 1 or homes.get(alias.name, node.module) != node.module
    ]
    plain_hits: list[tuple[int, str]] = [
      (node.lineno, f'{node.lineno} {alias.name}')
      for node in ast.walk(tree)
      if isinstance(node, ast.Import)
      for alias in node.names
      if alias.name.startswith('idunn.') and alias.name.count('.') > 1
    ]
    return [text for _, text in sorted(from_hits + plain_hits)]


def test_public_surface_matches_all() -> None:
  assert set(idunn.__all__) == EXPECTED_PUBLIC_NAMES


def test_testing_surface_matches_all() -> None:
  assert set(idunn.testing.__all__) == EXPECTED_TESTING_NAMES
  assert all(hasattr(idunn.testing, name) for name in EXPECTED_TESTING_NAMES)


def test_root_does_not_export_testing_names() -> None:
  # Test tooling stays one deliberate import away, so `from idunn import *` never drags it in.
  assert not EXPECTED_TESTING_NAMES & set(idunn.__all__)
  assert not any(hasattr(idunn, name) for name in EXPECTED_TESTING_NAMES)


def test_report_map_shape_is_pinned() -> None:
  assert set(idunn.ReportMap.__required_keys__) == {
    'root_package',
    'imported_modules',
    'skipped_modules',
    'registered_ports',
    'registered_adapters',
  }


def test_public_names_are_importable() -> None:
  missing = [name for name in EXPECTED_PUBLIC_NAMES if not hasattr(idunn, name)]
  assert not missing, f'missing from idunn: {missing}'


def test_tests_and_examples_import_public_names_from_their_home_barrel() -> None:
  homes: dict[str, str] = ImportProbe.homes()
  found: list[str] = [
    f'{path.relative_to(REPO_ROOT)}:{hit}'
    for root in ImportProbe.ROOTS
    for path in sorted(root.rglob('*.py'))
    for hit in ImportProbe.offenders(path, homes)
  ]
  assert not found, f'import public names from their barrel, the rest from a layer: {found}'


def test_import_probe_flags_public_names_and_module_paths(tmp_path: Path) -> None:
  sample: Path = tmp_path / 'sample.py'
  sample.write_text(
    'def nested() -> None:\n'
    '  from idunn.app import Port\n'
    'from idunn.domain.report import ReportMap\n'
    'from idunn.internal import InversionMapper\n'
    'from idunn import Adapter\n'
    'from .ports import AppleBasketPort\n'
    'import idunn.domain.report\n'
    'import idunn.internal, idunn\n'
    'from idunn.app import Harness\n'
    'from idunn.testing import Harness\n'
    'from idunn import Harness, Idunn\n'
    'from idunn.testing import Port\n',
    encoding='utf-8',
  )
  hits: list[str] = ImportProbe.offenders(sample, ImportProbe.homes())
  assert hits == [
    '2 idunn.app.Port',
    '3 idunn.domain.report.ReportMap',
    '7 idunn.domain.report',
    '9 idunn.app.Harness',
    '11 idunn.Harness',
    '12 idunn.testing.Port',
  ]
