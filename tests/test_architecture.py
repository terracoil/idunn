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
