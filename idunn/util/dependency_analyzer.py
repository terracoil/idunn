"""Dependency analysis utilities for Python projects."""

import ast
from pathlib import Path
from typing import Any


class DependencyAnalyzer(ast.NodeVisitor):
  """AST visitor that extracts import dependencies and class hierarchies."""

  def __init__(
    self,
    project_path: Path,
    include_external: bool = False,
    max_depth: int = 10,
  ) -> None:
    """Initialize analyzer with configuration.

    :param project_path: Root path of the project to analyze
    :param include_external: Include external (non-project) dependencies
    :param max_depth: Maximum depth for dependency traversal
    """
    self.project_path: Path = project_path
    self.include_external: bool = include_external
    self.max_depth: int = max_depth
    self.current_module: str = ''
    self.imports: set[str] = set()
    self.from_imports: dict[str, set[str]] = {}
    self.classes: dict[str, set[str]] = {}  # class_name -> set of parent classes

  def visit_Import(self, node: ast.Import) -> None:
    """Visitor hook for ``ast.Import`` — dispatched by ``NodeVisitor.visit`` (not a base override)."""
    for alias in node.names:
      self.imports.add(alias.name)
    self.generic_visit(node)

  def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
    """Visitor hook for ``ast.ImportFrom`` — dispatched by ``NodeVisitor.visit`` (not a base override)."""
    if node.module:
      bucket: set[str] = self.from_imports.setdefault(node.module, set())
      for alias in node.names:
        bucket.add(alias.name)
    self.generic_visit(node)

  def visit_ClassDef(self, node: ast.ClassDef) -> None:
    """Visitor hook for ``ast.ClassDef`` — dispatched by ``NodeVisitor.visit`` (not a base override)."""
    bases: list[str] = []
    for base in node.bases:
      if isinstance(base, ast.Name):
        bases.append(base.id)
      elif isinstance(base, ast.Attribute):
        bases.append(self._dotted_name(base))
    self.classes[node.name] = set(bases)
    self.generic_visit(node)

  @staticmethod
  def _dotted_name(attribute: ast.Attribute) -> str:
    """Render a ``module.Class`` attribute chain as a dotted string."""
    parts: list[str] = []
    current: ast.expr = attribute
    while isinstance(current, ast.Attribute):
      parts.append(current.attr)
      current = current.value
    if isinstance(current, ast.Name):
      parts.append(current.id)
    return '.'.join(reversed(parts))

  def analyze_file(self, file_path: Path) -> dict[str, Any] | None:
    """Analyze a single Python file for dependencies (``None`` on parse failure)."""
    result: dict[str, Any] | None = None
    try:
      content: str = file_path.read_text(encoding='utf-8')
      tree: ast.Module = ast.parse(content)

      # Reset per-file state before visiting.
      self.current_module = str(file_path.relative_to(self.project_path.parent))
      self.imports = set()
      self.from_imports = {}
      self.classes = {}
      self.visit(tree)

      module_name: str = str(
        file_path.relative_to(self.project_path.parent).with_suffix('')
      ).replace('/', '.')
      result = {
        'module': module_name,
        'imports': list(self.imports),
        'from_imports': {key: list(values) for key, values in self.from_imports.items()},
        'classes': {key: list(values) for key, values in self.classes.items()},
      }
    except Exception as exc:  # noqa: BLE001 — report and skip any unparseable file
      print(f'Error analyzing {file_path}: {exc}')
    return result

  def analyze(self) -> dict[str, dict[str, Any]]:
    """Analyze every Python file in the project."""
    results: dict[str, dict[str, Any]] = {}
    for py_file in self.project_path.rglob('*.py'):
      if '__pycache__' not in str(py_file):
        analysis: dict[str, Any] | None = self.analyze_file(py_file)
        if analysis:
          results[analysis['module']] = analysis
    return results

  def extract_package_dependencies(
    self,
    analysis: dict[str, dict[str, Any]],
  ) -> dict[str, set[str]]:
    """Extract package-level dependencies from analysis results."""
    project_name: str = self.project_path.name
    prefix: str = f'{project_name}.'
    package_deps: dict[str, set[str]] = {}
    for module, data in analysis.items():
      if not module.startswith(prefix):
        continue
      deps: set[str] = set()
      for from_module, _imports in data['from_imports'].items():
        if from_module and from_module.startswith(prefix):
          deps.add(from_module)
        elif from_module and from_module.startswith('.'):
          resolved: str = self._resolve_relative(module=module, from_module=from_module)
          if resolved.startswith(prefix):
            deps.add(resolved)
      for imported in data['imports']:
        if imported.startswith(prefix):
          deps.add(imported)
      package_deps[module] = deps
    return package_deps

  def extract_class_dependencies(
    self,
    analysis: dict[str, dict[str, Any]],
  ) -> dict[str, set[str]]:
    """Extract class-level dependencies from analysis results."""
    project_name: str = self.project_path.name
    prefix: str = f'{project_name}.'
    class_deps: dict[str, set[str]] = {}
    for module, data in analysis.items():
      if not module.startswith(prefix):
        continue
      for class_name, bases in data['classes'].items():
        full_class_name: str = f'{module}.{class_name}'
        deps: set[str] = {
          base for base in bases if not base.startswith(('ABC', 'Protocol', 'Enum'))
        }
        for from_module, imports in data['from_imports'].items():
          for imported in imports:
            # Heuristic: a capitalized, non-typing import is likely a class.
            if imported and imported[0].isupper() and not imported.startswith('TYPE_'):
              if from_module and from_module.startswith(prefix):
                deps.add(f'{from_module}.{imported}')
              elif from_module and from_module.startswith('.'):
                resolved: str = self._resolve_relative(module=module, from_module=from_module)
                if resolved.startswith(prefix):
                  deps.add(f'{resolved}.{imported}')
        class_deps[full_class_name] = deps
    return class_deps

  @staticmethod
  def _resolve_relative(*, module: str, from_module: str) -> str:
    """Resolve a relative ``from`` import to an absolute dotted module path."""
    parts: list[str] = module.split('.')
    if from_module == '.':
      return '.'.join(parts[:-1])
    level: int = len(from_module) - len(from_module.lstrip('.'))
    base: str = '.'.join(parts[:-level])
    suffix: str = from_module.lstrip('.')
    return f'{base}.{suffix}' if suffix else base

  def detect_cycles(self, package_deps: dict[str, set[str]]) -> list[list[str]]:
    """Detect circular dependencies using depth-first search."""
    cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: set[str] = set()
    for node in package_deps:
      if node not in visited:
        self._collect_cycles(
          node=node,
          path=[],
          package_deps=package_deps,
          visited=visited,
          rec_stack=rec_stack,
          cycles=cycles,
        )
    return cycles

  def _collect_cycles(
    self,
    *,
    node: str,
    path: list[str],
    package_deps: dict[str, set[str]],
    visited: set[str],
    rec_stack: set[str],
    cycles: list[list[str]],
  ) -> None:
    """Recursive DFS helper accumulating cycles into ``cycles`` (mutates the shared sets)."""
    visited.add(node)
    rec_stack.add(node)
    current_path: list[str] = [*path, node]
    for neighbor in package_deps.get(node, set()):
      if neighbor in rec_stack:
        cycle_start: int = current_path.index(neighbor)
        cycles.append([*current_path[cycle_start:], neighbor])
      elif neighbor not in visited:
        self._collect_cycles(
          node=neighbor,
          path=current_path,
          package_deps=package_deps,
          visited=visited,
          rec_stack=rec_stack,
          cycles=cycles,
        )
    rec_stack.remove(node)

  def filter_results(
    self,
    analysis: dict[str, dict[str, Any]],
    filter_package: str,
  ) -> dict[str, dict[str, Any]]:
    """Filter analysis results to a specific package prefix."""
    return {module: data for module, data in analysis.items() if module.startswith(filter_package)}
