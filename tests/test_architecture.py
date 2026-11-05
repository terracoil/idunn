"""Architecture tests: the four layers import downhill only, and nothing loiters at the root.
``testing`` sits on top as a fifth package that may import ``app`` and nothing else, and that no
layer may import, so production code cannot lean on test tooling even by accident. Inside the
package, siblings import each other by single-dot relative paths and other layers through their
barrels, never through the root barrel or a module path, and no module import graph has a cycle.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / 'idunn'
LAYERS = ('app', 'domain', 'internal', 'testing', 'util')
ALLOWED = {
  'app': {'app', 'domain', 'internal', 'util'},
  'domain': {'domain', 'util'},
  'internal': {'internal', 'domain', 'util'},
  'testing': {'testing', 'app'},
  'util': {'util'},
}


class LayerProbe:
  """Resolves each module's layer and the internal layers it imports from."""

  @classmethod
  def misspelled(cls, tree: ast.Module, package: list[str]) -> list[str]:
    """Return ``line import`` for each import in ``tree`` that breaks the package's spelling rules.
    Three ways to get it wrong: a relative import that climbs (``..``), a module path
    (``idunn.domain.catalog``, or ``from idunn.domain import catalog``) instead of a barrel, and
    the root barrel (``idunn``), which no layer needs and which hides which layer a name really
    comes from.
    """
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
      if isinstance(node, ast.ImportFrom):
        module: str = cls._resolved(node, package)
        climbs: bool = node.level > 1
        absolute: bool = node.level == 0 and (
          cls._wrong_absolute(module) or cls._names_a_module(module, node)
        )
        if climbs or absolute:
          hits.append((node.lineno, f'{node.lineno} from {"." * node.level}{node.module or ""}'))
      elif isinstance(node, ast.Import):
        hits.extend(
          (node.lineno, f'{node.lineno} import {alias.name}')
          for alias in node.names
          if cls._wrong_absolute(alias.name)
        )
    return [text for _, text in sorted(hits)]

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

  @staticmethod
  def layer_of_path(path: Path) -> str | None:
    """Layer that owns a source file, or None for a root-level or non-layer module."""
    parts = path.relative_to(PACKAGE_ROOT).parts
    return parts[0] if len(parts) >= 2 and parts[0] in LAYERS else None

  @staticmethod
  def _containing_package(path: Path) -> list[str]:
    return list(path.relative_to(PACKAGE_ROOT.parent).with_suffix('').parts[:-1])

  @classmethod
  def _import_targets(cls, node: ast.AST, package: list[str]) -> list[str]:
    targets: list[str] = []
    if isinstance(node, ast.Import):
      targets = [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
      module: str = cls._resolved(node, package)
      # `from idunn import app`, or `from .. import app`, names a layer through the root barrel.
      targets = (
        [f'{module}.{alias.name}' for alias in node.names] if module == 'idunn' else [module]
      )
    return targets

  @staticmethod
  def _names_a_module(module: str, node: ast.ImportFrom) -> bool:
    # `from idunn.internal import inversion_mapper` is a module path in a barrel's coat. Compared
    # by name rather than by asking the file system, which on macOS thinks `Idunn` is `idunn.py`.
    folder: Path = PACKAGE_ROOT.parent.joinpath(*module.split('.'))
    modules: set[str] = (
      {path.stem for path in folder.glob('*.py')}
      | {path.parent.name for path in folder.glob('*/__init__.py')}
      if module.startswith('idunn.') and folder.is_dir()
      else set()
    )
    return any(alias.name in modules for alias in node.names)

  @staticmethod
  def _resolved(node: ast.ImportFrom, package: list[str]) -> str:
    base: list[str] = package[: len(package) - (node.level - 1)] if node.level else []
    suffix: list[str] = node.module.split('.') if node.module else []
    return '.'.join([*base, *suffix])

  @staticmethod
  def _wrong_absolute(module: str) -> bool:
    # The root barrel itself, or anything deeper than a layer barrel such as `idunn.domain`.
    return module == 'idunn' or (module.startswith('idunn.') and module.count('.') > 1)

  @staticmethod
  def _layer_of_dotted(dotted: str) -> str | None:
    parts = dotted.split('.')
    return parts[1] if parts[0] == 'idunn' and len(parts) >= 2 and parts[1] in LAYERS else None


class ImportGraph:
  """Module-level import edges under one package, and the cycles among them.
  An edge goes to the module a name is imported from: ``from .catalog import Catalog`` is an edge
  to ``catalog``, and ``from . import catalog`` too, while ``from idunn.domain import Catalog``
  is an edge to the ``idunn.domain`` barrel. Parent packages initialising first is containment,
  not dependency, so it adds no edge; a module importing its own layer's barrel does, and should.
  """

  @classmethod
  def of(cls, root: Path) -> dict[str, set[str]]:
    """Return every module under the package directory ``root`` and the modules it imports."""
    modules: dict[str, Path] = {cls._name(path, root): path for path in sorted(root.rglob('*.py'))}
    return {
      name: {
        target
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8')))
        for target in cls._targets(node, cls._package(name, path), modules)
      }
      for name, path in modules.items()
    }

  @staticmethod
  def cycles(graph: Mapping[str, set[str]]) -> list[list[str]]:
    """Return each strongly connected component with more than one module, or a self-import.
    Tarjan's algorithm, iterative so a deep package cannot hit the recursion limit.
    """
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    found: list[list[str]] = []
    for start in sorted(graph):
      if start in index:
        continue
      work: list[tuple[str, list[str]]] = [(start, sorted(graph.get(start, ())))]
      index[start] = low[start] = len(index)
      stack.append(start)
      on_stack.add(start)
      while work:
        node, pending = work[-1]
        if pending:
          child: str = pending.pop()
          if child not in index:
            index[child] = low[child] = len(index)
            stack.append(child)
            on_stack.add(child)
            work.append((child, sorted(graph.get(child, ()))))
          elif child in on_stack:
            low[node] = min(low[node], index[child])
          continue
        work.pop()
        if work:
          low[work[-1][0]] = min(low[work[-1][0]], low[node])
        if low[node] == index[node]:
          component: list[str] = []
          member: str = ''
          while member != node:
            member = stack.pop()
            on_stack.discard(member)
            component.append(member)
          if len(component) > 1 or node in graph.get(node, ()):
            found.append(sorted(component))
    return found

  @staticmethod
  def _name(path: Path, root: Path) -> str:
    parts: tuple[str, ...] = path.relative_to(root.parent).with_suffix('').parts
    return '.'.join(parts[:-1] if parts[-1] == '__init__' else parts)

  @staticmethod
  def _package(name: str, path: Path) -> list[str]:
    parts: list[str] = name.split('.')
    return parts if path.name == '__init__.py' else parts[:-1]

  @staticmethod
  def _targets(node: ast.AST, package: list[str], modules: Mapping[str, Path]) -> list[str]:
    targets: list[str] = []
    if isinstance(node, ast.Import):
      targets = [alias.name for alias in node.names if alias.name in modules]
    elif isinstance(node, ast.ImportFrom):
      base: str = LayerProbe._resolved(node, package)
      named: list[str] = [f'{base}.{alias.name}' for alias in node.names]
      targets = [name if name in modules else base for name in named]
      targets = [target for target in targets if target in modules]
    return targets


def test_no_modules_outside_the_known_packages() -> None:
  stray: list[str] = []
  for path in PACKAGE_ROOT.rglob('*.py'):
    parts = path.relative_to(PACKAGE_ROOT).parts
    if len(parts) == 1:
      if parts[0] != '__init__.py':
        stray.append(str(path.relative_to(PACKAGE_ROOT)))
    elif parts[0] not in LAYERS:
      stray.append(str(path.relative_to(PACKAGE_ROOT)))
  assert not stray, f'Modules outside app/domain/internal/testing/util: {stray}'


def test_testing_holds_only_its_barrel() -> None:
  # The implementation lives in app beside the facade it drives; this package only re-exports it.
  modules = sorted(path.relative_to(PACKAGE_ROOT).as_posix() for path in PACKAGE_ROOT.rglob('*.py'))
  assert [module for module in modules if module.startswith('testing/')] == ['testing/__init__.py']


def test_no_layer_may_import_testing() -> None:
  assert all('testing' not in ALLOWED[layer] for layer in LAYERS if layer != 'testing')
  node = ast.parse('from idunn.testing import Harness').body[0]
  targets = LayerProbe._import_targets(node, ['idunn', 'app'])
  assert LayerProbe._layer_of_dotted(targets[0]) == 'testing'


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


def test_the_package_imports_siblings_relatively_and_other_layers_by_barrel() -> None:
  found: list[str] = [
    f'{path.relative_to(PACKAGE_ROOT)}:{hit}'
    for path in sorted(PACKAGE_ROOT.rglob('*.py'))
    for hit in LayerProbe.misspelled(
      ast.parse(path.read_text(encoding='utf-8')), LayerProbe._containing_package(path)
    )
  ]
  assert not found, f'use `.sibling` within a layer and `idunn.<layer>` across: {found}'


def test_the_spelling_probe_flags_climbs_module_paths_and_the_root_barrel() -> None:
  sample: ast.Module = ast.parse(
    'from .catalog import Catalog\n'
    'from idunn.domain import Catalog\n'
    'from ..domain import Catalog\n'
    'from idunn.domain.catalog import Catalog\n'
    'from idunn import Idunn\n'
    'from .. import app\n'
    'import idunn.domain.catalog\n'
    'import idunn.domain, idunn\n'
    'from idunn.internal import InversionMapper, inversion_mapper\n'
    'from idunn.app import Idunn\n'
  )

  assert LayerProbe.misspelled(sample, ['idunn', 'app']) == [
    '3 from ..domain',
    '4 from idunn.domain.catalog',
    '5 from idunn',
    '6 from ..',
    '7 import idunn.domain.catalog',
    '8 import idunn',
    '9 from idunn.internal',
  ]


@pytest.mark.parametrize(
  ('source', 'package', 'layer'),
  [
    ('from idunn import app', ['idunn', 'domain'], 'app'),  # passed the matrix and ran, before
    ('from .. import app', ['idunn', 'internal'], 'app'),
    ('from idunn import Idunn', ['idunn', 'util'], None),  # no layer here; misspelled() has it
  ],
)
def test_imports_through_the_root_barrel_name_the_layer_they_reach(
  source: str, package: list[str], layer: str | None
) -> None:
  node: ast.stmt = ast.parse(source).body[0]
  layers: list[str | None] = [
    LayerProbe._layer_of_dotted(target) for target in LayerProbe._import_targets(node, package)
  ]
  assert layers == [layer]


@pytest.mark.parametrize('root', ['idunn', 'examples'])
def test_no_module_import_cycles(root: str) -> None:
  assert ImportGraph.cycles(ImportGraph.of(REPO_ROOT / root)) == []


def test_the_cycle_finder_finds_a_loop_inside_one_layer_and_ignores_a_diamond() -> None:
  # The intra-layer loop Jody built in a scratch copy: it passed every other test, and ran.
  graph: dict[str, set[str]] = {
    'port_registry': {'lazy_plan'},
    'lazy_plan': {'constructor_planner'},
    'constructor_planner': {'decorator_support'},
    'decorator_support': {'port_registry'},
    'top': {'left', 'right'},
    'left': {'bottom'},
    'right': {'bottom'},
    'bottom': set(),
    'narcissus': {'narcissus'},
  }

  assert ImportGraph.cycles(graph) == [
    ['constructor_planner', 'decorator_support', 'lazy_plan', 'port_registry'],
    ['narcissus'],
  ]


def test_the_import_graph_resolves_names_to_modules_and_barrels(tmp_path: Path) -> None:
  package: Path = tmp_path / 'pkg'
  (package / 'layer').mkdir(parents=True)
  (package / '__init__.py').write_text('', encoding='utf-8')
  (package / 'layer' / '__init__.py').write_text('from .one import One\n', encoding='utf-8')
  (package / 'layer' / 'one.py').write_text('from . import two\n', encoding='utf-8')
  (package / 'layer' / 'two.py').write_text('from pkg.layer import One\n', encoding='utf-8')

  graph: dict[str, set[str]] = ImportGraph.of(package)

  assert graph['pkg.layer'] == {'pkg.layer.one'}
  assert graph['pkg.layer.one'] == {'pkg.layer.two'}
  assert graph['pkg.layer.two'] == {'pkg.layer'}  # its own layer's barrel: a cycle, as it should be
  assert ImportGraph.cycles(graph) == [['pkg.layer', 'pkg.layer.one', 'pkg.layer.two']]
