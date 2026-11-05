"""Every example runs, prints exactly its ``expected*.txt``, and registers what its docstring says.
Examples are found by globbing ``examples/*/*/main.py``, so a new one is tested the day it lands,
and one with no expected file fails rather than passing unread. ``expected.txt`` runs with
``IDUNN_ENV`` unset and ``expected.<env>.txt`` with ``IDUNN_ENV=<env>``, each in a subprocess with
a scrubbed environment, because a stray ``IDUNN_ENV`` in a developer's shell is precisely the kind
of thing an example should not depend on. The README's "Normal usage" listings are pinned to
``examples/classy/simple`` too, so the copy readers paste cannot drift from the copy the suite runs.
"""

import ast
import importlib
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
    """Pair every example with each of its expected files, as ``(package, env, expected)``.
    A package with none still gets a run against a missing ``expected.txt``, which fails loudly.
    """
    return tuple(
      (package, Examples.environment(expected), expected)
      for package in Examples.packages()
      for expected in (
        sorted(Examples.directory(package).glob('expected*.txt'))
        or [Examples.directory(package) / 'expected.txt']
      )
    )

  @staticmethod
  def directory(package: str) -> Path:
    """Return the source directory of ``package``."""
    return REPO_ROOT.joinpath(*package.split('.'))

  @staticmethod
  def environment(expected: Path) -> str | None:
    """Read the environment from the name: ``prod`` for ``expected.prod.txt``, else ``None``."""
    parts: list[str] = expected.name.split('.')
    return '.'.join(parts[1:-1]) or None

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

  @staticmethod
  def declared(docstring: str) -> tuple[list[str], list[str]]:
    """Parse ``Registers: Port, Port; Adapter, Adapter``, indented continuation lines included."""
    lines: list[str] = docstring.splitlines()
    start: int = next(
      (index for index, line in enumerate(lines) if line.startswith('Registers:')), len(lines)
    )
    assert start < len(lines), 'the package docstring needs a "Registers: ports; adapters" line'
    block: list[str] = [
      lines[start].removeprefix('Registers:'),
      *takewhile(lambda line: line.startswith(' '), lines[start + 1 :]),
    ]
    ports, adapters = ' '.join(block).split(';')
    return Examples.names(ports.split(',')), Examples.names(adapters.split(','))

  @staticmethod
  def names(items: Iterable[str]) -> list[str]:
    """Sort bare class names: the last dotted part of each, stripped, with blanks dropped."""
    return sorted(item.strip().rpartition('.')[2] for item in items if item.strip())


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
  ids=[f'{package}-{environment or "default"}' for package, environment, _ in Examples.runs()],
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


@pytest.mark.usefixtures('forget_examples')
@pytest.mark.parametrize('package', Examples.packages())
def test_example_registers_what_its_docstring_lists(package: str) -> None:
  report: ReportMap = Idunn().autodiscover(package)
  ports, adapters = Examples.declared(importlib.import_module(package).__doc__ or '')

  assert Examples.names(report['registered_ports']) == ports
  assert Examples.names(report['registered_adapters']) == adapters


def test_readme_normal_usage_quotes_the_simple_example_file_for_file() -> None:
  listings: list[tuple[str, str]] = Readme.listings()
  directory: Path = Examples.directory(Readme.EXAMPLE)

  assert sorted(name for name, _ in listings) == ['adapters.py', 'main.py', 'ports.py']
  assert [(name, Readme.quoted(directory / name)) for name, _ in listings] == listings
