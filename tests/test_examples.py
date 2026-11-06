"""Every example runs, prints exactly its ``expected*.txt``, and registers what its docstring says.
Examples are found by globbing ``examples/*/*/main.py``, so a new one is tested the day it lands.
Its ``__init__`` docstring makes two promises. ``Environments:`` names the runs: each name is
``IDUNN_ENV=<name>`` against ``expected.<name>.txt``, except ``unset``, which runs with
``IDUNN_ENV`` unset against ``expected.txt``, and the files shipped must match the line exactly, so
a missing or stray one fails rather than passing unread. ``Registers:`` names, relative to the
package, every class discovery finds, so a class that moves module is caught too. Each run is a
subprocess with a scrubbed environment, because a stray ``IDUNN_ENV`` in a developer's shell is
precisely the kind of thing an example should not depend on. The README's "Normal usage" listings
are pinned to ``examples/classy/simple`` too, so the copy readers paste cannot drift from the copy
the suite runs.
"""

import ast
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator
from itertools import takewhile
from pathlib import Path

import pytest

from idunn import Idunn, ReportMap

pytestmark = pytest.mark.integration

REPO_ROOT: Path = Path(__file__).resolve().parent.parent


class Examples:
  """Finds the example packages and reads what each one promises."""

  # The run with no IDUNN_ENV at all, which Idunn treats as `local` but the example need not name.
  UNSET: str = 'unset'

  @staticmethod
  def packages() -> tuple[str, ...]:
    """Name every example package: every directory, two below ``examples``, with a ``main.py``."""
    return tuple(
      sorted(
        '.'.join(main.parent.relative_to(REPO_ROOT).parts)
        for main in REPO_ROOT.glob('examples/*/*/main.py')
      )
    )

  @staticmethod
  def runs() -> tuple[tuple[str, str | None, Path], ...]:
    """Pair every example with each environment it declares, as ``(package, env, expected)``.
    The expected file need not exist: a run against a missing one fails loudly, and so does
    :func:`test_example_ships_exactly_the_expected_files_its_environments_line_names`.
    """
    return tuple(
      (
        package,
        None if environment == Examples.UNSET else environment,
        Examples.directory(package) / Examples.expected_name(environment),
      )
      for package in Examples.packages()
      for environment in Examples.environments(package)
    )

  @staticmethod
  def directory(package: str) -> Path:
    """Return the source directory of ``package``."""
    return REPO_ROOT.joinpath(*package.split('.'))

  @staticmethod
  def docstring(package: str) -> str:
    """Read the package docstring from source, uncleaned, without importing anything."""
    source: str = (Examples.directory(package) / '__init__.py').read_text(encoding='utf-8')
    return ast.get_docstring(ast.parse(source), clean=False) or ''

  @staticmethod
  def environments(package: str) -> list[str]:
    """Return the names on the ``Environments:`` line, in order; none if there is no such line."""
    return Examples.names(
      (Examples.field(Examples.docstring(package), 'Environments') or '').split(',')
    )

  @staticmethod
  def expected_name(environment: str) -> str:
    """Name the file a run compares against: ``expected.txt`` for ``unset``, else by environment."""
    return 'expected.txt' if environment == Examples.UNSET else f'expected.{environment}.txt'

  @staticmethod
  def field(docstring: str, name: str) -> str | None:
    """Return the text after ``<name>:``, indented continuation lines included, or ``None``."""
    lines: list[str] = docstring.splitlines()
    start: int | None = next(
      (index for index, line in enumerate(lines) if line.startswith(f'{name}:')), None
    )
    return (
      None
      if start is None
      else ' '.join(
        [
          lines[start].removeprefix(f'{name}:'),
          *takewhile(lambda line: line.startswith(' '), lines[start + 1 :]),
        ]
      )
    )

  @staticmethod
  def declared(docstring: str) -> tuple[list[str], list[str]]:
    """Parse ``Registers: module.Port, ...; module.Adapter, ...`` into two sorted lists."""
    block: str | None = Examples.field(docstring, 'Registers')
    assert block is not None, 'the package docstring needs a "Registers: ports; adapters" line'
    ports, adapters = block.split(';')
    return sorted(Examples.names(ports.split(','))), sorted(Examples.names(adapters.split(',')))

  @staticmethod
  def names(items: Iterable[str]) -> list[str]:
    """Strip each item and drop the blanks, keeping the order."""
    return [item.strip() for item in items if item.strip()]

  @staticmethod
  def relative(package: str, qualified: Iterable[str]) -> list[str]:
    """Sort discovered names relative to ``package``; one from elsewhere keeps its full name."""
    return sorted(name.removeprefix(f'{package}.') for name in qualified)

  @staticmethod
  def scrubbed_env(environment: str | None) -> dict[str, str]:
    """Build just enough environment to start Python, plus ``IDUNN_ENV`` when the run has one."""
    base: dict[str, str] = {
      'PATH': os.environ.get('PATH', os.defpath),
      'HOME': os.environ.get('HOME', str(Path.home())),
      'PYTHONDONTWRITEBYTECODE': '1',
      'PYTHONPATH': str(REPO_ROOT),
    }
    return base if environment is None else base | {'IDUNN_ENV': environment}


class Readme:
  """The README's "Normal usage" listings, which quote ``examples/classy/simple`` file for file."""

  EXAMPLE: str = 'examples.classy.simple'
  # The one documented difference: the repo's copy sits two packages deeper than the reader's app.
  EXAMPLE_ROOT: str = "'examples.classy.simple'"
  README_ROOT: str = "'my_app'"

  @staticmethod
  def listings() -> list[tuple[str, str]]:
    """Pair each ``# my_app/<file>`` block under "Normal usage" with the code beneath its header.
    A list, not a dict: a second block under the same name must fail the test, not hide the first.
    """
    text: str = (REPO_ROOT / 'README.md').read_text(encoding='utf-8')
    section: str = text.partition('\n## Normal usage\n')[2].partition('\n## ')[0]
    blocks: list[str] = re.findall(r'```python\n(.*?)```', section, flags=re.DOTALL)
    return [
      (header.removeprefix('# my_app/'), body)
      for header, _, body in (block.partition('\n') for block in blocks)
      if header.startswith('# my_app/')
    ]

  @staticmethod
  def quoted(path: Path) -> str:
    """Return ``path`` as the README quotes it: no module docstring, and the reader's root."""
    source: str = path.read_text(encoding='utf-8')
    tree: ast.Module = ast.parse(source)
    skipped: int = (tree.body[0].end_lineno or 0) if ast.get_docstring(tree) is not None else 0
    body: str = ''.join(source.splitlines(keepends=True)[skipped:]).lstrip('\n')
    return body.replace(Readme.EXAMPLE_ROOT, Readme.README_ROOT)


@pytest.fixture
def forget_examples() -> Iterator[None]:
  """Drop the example modules a test imported, so the next import of them starts from source."""
  before: frozenset[str] = frozenset(sys.modules)
  yield
  for name in frozenset(sys.modules) - before:
    if name.partition('.')[0] == 'examples':
      del sys.modules[name]


def test_examples_are_found() -> None:
  # A broken glob would make both parametrised tests vanish rather than fail.
  assert len(Examples.packages()) >= 4


@pytest.mark.parametrize(
  ('package', 'environment', 'expected'),
  Examples.runs(),
  ids=[f'{package}-{environment or Examples.UNSET}' for package, environment, _ in Examples.runs()],
)
def test_example_prints_its_expected_output(
  package: str, environment: str | None, expected: Path
) -> None:
  result: subprocess.CompletedProcess[str] = subprocess.run(
    [sys.executable, '-m', f'{package}.main'],
    cwd=REPO_ROOT,
    env=Examples.scrubbed_env(environment),
    capture_output=True,
    text=True,
    check=False,
    timeout=60,
  )

  assert result.returncode == 0, result.stderr
  assert result.stdout == expected.read_text(encoding='utf-8')


@pytest.mark.parametrize('package', Examples.packages())
def test_example_ships_exactly_the_expected_files_its_environments_line_names(package: str) -> None:
  environments: list[str] = Examples.environments(package)
  shipped: list[str] = sorted(
    path.name for path in Examples.directory(package).glob('expected*.txt')
  )

  assert environments, 'the package docstring needs an "Environments: ..." line'
  assert shipped == sorted(map(Examples.expected_name, environments))


@pytest.mark.usefixtures('forget_examples')
@pytest.mark.parametrize('package', Examples.packages())
def test_example_registers_what_its_docstring_lists(package: str) -> None:
  report: ReportMap = Idunn().autodiscover(package)
  ports, adapters = Examples.declared(Examples.docstring(package))

  assert Examples.relative(package, report['registered_ports']) == ports
  assert Examples.relative(package, report['registered_adapters']) == adapters


def test_readme_normal_usage_quotes_the_simple_example_file_for_file() -> None:
  listings: list[tuple[str, str]] = Readme.listings()
  directory: Path = Examples.directory(Readme.EXAMPLE)

  assert sorted(name for name, _ in listings) == ['adapters.py', 'main.py', 'ports.py']
  assert [(name, Readme.quoted(directory / name)) for name, _ in listings] == listings
