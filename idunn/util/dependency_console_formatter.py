"""Console (colored text) formatter for dependency-analysis results."""

from typing import Any


class ConsoleFormatter:
  """Renders a dependency-analysis result as a colored, human-readable report."""

  def __init__(
    self,
    show_classes: bool = False,
    show_cycles: bool = False,
    colors: dict[str, str] | None = None,
  ) -> None:
    """Configure which sections to render and the ANSI color palette."""
    self.show_classes: bool = show_classes
    self.show_cycles: bool = show_cycles
    self.colors: dict[str, str] = colors if colors is not None else {}

  def format(self, analysis_result: dict[str, Any]) -> str:
    """Render package deps, optional class deps, and optional cycles as text."""
    lines: list[str] = [self._heading('Package dependencies')]
    lines.extend(self._dependency_lines(analysis_result.get('package_dependencies', {})))
    if self.show_classes:
      lines.append(self._heading('Class dependencies'))
      lines.extend(self._dependency_lines(analysis_result.get('class_dependencies', {})))
    if self.show_cycles:
      lines.append(self._heading('Circular dependencies'))
      lines.extend(self._cycle_lines(analysis_result.get('cycles', [])))
    return '\n'.join(lines)

  def _heading(self, text: str) -> str:
    """Render a colored section heading."""
    blue: str = self.colors.get('blue', '')
    nc: str = self.colors.get('nc', '')
    return f'{blue}== {text} =={nc}'

  def _dependency_lines(self, dependencies: dict[str, set[str]]) -> list[str]:
    """Render each ``source -> targets`` mapping as an indented block."""
    lines: list[str] = []
    for source in sorted(dependencies):
      lines.append(f'  {source}')
      lines.extend(f'    -> {target}' for target in sorted(dependencies[source]))
    return lines

  def _cycle_lines(self, cycles: list[list[str]]) -> list[str]:
    """Render each detected cycle, or a clean-bill line when none exist."""
    if not cycles:
      green: str = self.colors.get('green', '')
      nc: str = self.colors.get('nc', '')
      return [f'  {green}none detected{nc}']
    return [f'  {" -> ".join(cycle)}' for cycle in cycles]
