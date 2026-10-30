"""The public surface lives in the top-level ``idunn`` package, and tests and examples use it there.

Names a user is never meant to import stay in their layer package (``idunn.domain``,
``idunn.internal``, ``idunn.util``) and are imported from there; nothing comes from a module path.
"""

import ast
from pathlib import Path

import idunn

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


class ImportProbe:
  """Finds absolute ``from idunn.<...> import`` statements that bypass the public barrel."""

  ROOTS: tuple[Path, ...] = (REPO_ROOT / 'tests', REPO_ROOT / 'examples')

  @staticmethod
  def offenders(path: Path, public: frozenset[str]) -> list[str]:
    """Return ``line module.name`` for each public name or module path imported below ``idunn``.

    Relative imports (``level > 0``) and bare ``from . import x`` (``module is None``) are
    skipped: they never name the ``idunn`` package. Hits are ordered by line number, because
    ``ast.walk`` is breadth-first.
    """
    tree: ast.Module = ast.parse(path.read_text(encoding='utf-8'))
    hits: list[tuple[int, str]] = [
      (node.lineno, f'{node.lineno} {node.module}.{alias.name}')
      for node in ast.walk(tree)
      if isinstance(node, ast.ImportFrom)
      and node.level == 0
      and node.module is not None
      and node.module.startswith('idunn.')
      for alias in node.names
      if node.module.count('.') > 1 or alias.name in public
    ]
    return [text for _, text in sorted(hits)]


def test_public_surface_matches_all() -> None:
  assert set(idunn.__all__) == EXPECTED_PUBLIC_NAMES


def test_public_names_are_importable() -> None:
  missing = [name for name in EXPECTED_PUBLIC_NAMES if not hasattr(idunn, name)]
  assert not missing, f'missing from idunn: {missing}'


def test_tests_and_examples_import_public_names_from_idunn() -> None:
  public: frozenset[str] = frozenset(idunn.__all__)
  found: list[str] = [
    f'{path.relative_to(REPO_ROOT)}:{hit}'
    for root in ImportProbe.ROOTS
    for path in sorted(root.rglob('*.py'))
    for hit in ImportProbe.offenders(path, public)
  ]
  assert not found, f'import public names from idunn, the rest from a layer package: {found}'


def test_import_probe_flags_public_names_and_module_paths(tmp_path: Path) -> None:
  sample: Path = tmp_path / 'sample.py'
  sample.write_text(
    'def nested() -> None:\n'
    '  from idunn.app import Port\n'
    'from idunn.domain.report import ReportMap\n'
    'from idunn.internal import InversionMapper\n'
    'from idunn import Adapter\n'
    'from .ports import AppleBasketPort\n',
    encoding='utf-8',
  )
  hits: list[str] = ImportProbe.offenders(sample, frozenset(idunn.__all__))
  assert hits == ['2 idunn.app.Port', '3 idunn.domain.report.ReportMap']
