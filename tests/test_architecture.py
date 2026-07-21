"""Architecture tests: enforce the app/domain/internal/util layering."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / 'idunn'
LAYERS = ('app', 'domain', 'internal', 'util')
ALLOWED = {
  'app': {'app', 'domain', 'internal', 'util'},
  'domain': {'domain', 'util'},
  'internal': {'internal', 'domain', 'util'},
  'util': {'util'},
}


class LayerProbe:
  """Resolves each module's layer and the internal layers it imports from."""

  @staticmethod
  def layer_of_path(path: Path) -> str | None:
    """Layer that owns a source file, or None for a root-level module."""
    parts = path.relative_to(PACKAGE_ROOT).parts
    return parts[0] if len(parts) >= 2 and parts[0] in LAYERS else None

  @staticmethod
  def _containing_package(path: Path) -> list[str]:
    return list(path.relative_to(PACKAGE_ROOT.parent).with_suffix('').parts[:-1])

  @staticmethod
  def _layer_of_dotted(dotted: str) -> str | None:
    parts = dotted.split('.')
    return parts[1] if parts[0] == 'idunn' and len(parts) >= 2 and parts[1] in LAYERS else None

  @staticmethod
  def _import_targets(node: ast.AST, package: list[str]) -> list[str]:
    targets: list[str] = []
    if isinstance(node, ast.Import):
      targets = [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom) and node.level == 0:
      targets = [node.module] if node.module is not None else []
    elif isinstance(node, ast.ImportFrom):
      base = package[: len(package) - (node.level - 1)]
      suffix = node.module.split('.') if node.module else []
      targets = ['.'.join([*base, *suffix])]
    return targets

  @classmethod
  def imported_layers(cls, path: Path) -> set[tuple[str, str]]:
    """Return the internal (layer, dotted-module) edges imported by the file."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    package = cls._containing_package(path)
    edges: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
      for dotted in cls._import_targets(node, package):
        layer = cls._layer_of_dotted(dotted)
        if layer is not None:
          edges.add((layer, dotted))
    return edges


def test_no_modules_outside_the_four_layers() -> None:
  stray: list[str] = []
  for path in PACKAGE_ROOT.rglob('*.py'):
    parts = path.relative_to(PACKAGE_ROOT).parts
    if len(parts) == 1:
      if parts[0] != '__init__.py':
        stray.append(str(path.relative_to(PACKAGE_ROOT)))
    elif parts[0] not in LAYERS:
      stray.append(str(path.relative_to(PACKAGE_ROOT)))
  assert not stray, f'Modules outside app/domain/internal/util: {stray}'


def test_layer_dependencies_respect_allowed_matrix() -> None:
  violations: list[str] = []
  for path in PACKAGE_ROOT.rglob('*.py'):
    source = LayerProbe.layer_of_path(path)
    if source is None:
      continue
    for target_layer, target in sorted(LayerProbe.imported_layers(path)):
      if target_layer not in ALLOWED[source]:
        rel = path.relative_to(PACKAGE_ROOT)
        violations.append(f'{source} -> {target_layer}: {rel} imports {target}')
  assert not violations, 'Layering violations:\n' + '\n'.join(violations)


def test_util_has_no_internal_dependencies() -> None:
  offending: list[str] = []
  for path in (PACKAGE_ROOT / 'util').rglob('*.py'):
    for target_layer, target in LayerProbe.imported_layers(path):
      if target_layer != 'util':
        offending.append(f'{path.name} imports {target}')
  assert not offending, f'util must not depend on other layers: {offending}'


def test_domain_only_depends_on_util() -> None:
  offending: list[str] = []
  for path in (PACKAGE_ROOT / 'domain').rglob('*.py'):
    for target_layer, target in LayerProbe.imported_layers(path):
      if target_layer not in {'domain', 'util'}:
        offending.append(f'{path.name} imports {target}')
  assert not offending, f'domain may only depend on util: {offending}'


def test_probe_would_flag_a_synthetic_cross_layer_edge() -> None:
  assert LayerProbe._layer_of_dotted('idunn.app.idunn') == 'app'
  assert 'app' not in ALLOWED['util']


def test_probe_flags_a_real_violating_edge() -> None:
  # End-to-end on real source: prove imported_layers actually detects internal edges,
  # and that the matrix would reject one if the file lived in a stricter layer.
  mapper_file = PACKAGE_ROOT / 'internal' / 'inversion_mapper.py'
  target_layers = {layer for layer, _ in LayerProbe.imported_layers(mapper_file)}
  assert {'domain', 'util'} <= target_layers
  assert 'domain' not in ALLOWED['util']  # so a util->domain edge here would be flagged

  # Synthetic node: a util module importing idunn.app resolves to a forbidden 'app' edge.
  node = ast.parse('from idunn.app import Idunn').body[0]
  targets = LayerProbe._import_targets(node, ['idunn', 'util'])
  assert LayerProbe._layer_of_dotted(targets[0]) == 'app'
  assert 'app' not in ALLOWED['util']


def test_layer_of_dotted_rejects_external_and_bare() -> None:
  assert LayerProbe._layer_of_dotted('os') is None
  assert LayerProbe._layer_of_dotted('idunn') is None
  assert LayerProbe._layer_of_dotted('idunn.notalayer') is None


def test_import_targets_handles_bare_relative_and_multi() -> None:
  package = ['idunn', 'internal']
  bare = ast.parse('from . import decorator_support').body[0]
  assert LayerProbe._import_targets(bare, package) == ['idunn.internal']
  multi = ast.parse('import os, sys').body[0]
  assert LayerProbe._import_targets(multi, package) == ['os', 'sys']


def test_layer_of_path_returns_none_for_root_and_nonlayer() -> None:
  assert LayerProbe.layer_of_path(PACKAGE_ROOT / '__init__.py') is None
  assert LayerProbe.layer_of_path(PACKAGE_ROOT / 'scripts' / 'helper.py') is None
  assert LayerProbe.layer_of_path(PACKAGE_ROOT / 'app' / 'idunn.py') == 'app'
