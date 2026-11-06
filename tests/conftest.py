"""Shared fixtures: a singleton wiped clean around every test, a package writer, a fast switch."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from idunn import Idunn

from _support import PackageWriter


@pytest.fixture(autouse=True)
def _reset_idunn() -> Iterator[None]:
  """Give every test a clean singleton bound to a deterministic environment."""
  Idunn().reset(environment='local')
  yield
  Idunn().reset(environment='local')


@pytest.fixture
def eager_switching() -> Iterator[None]:
  """Make the interpreter swap threads every microsecond, so races show up in a test this short."""
  previous = sys.getswitchinterval()
  sys.setswitchinterval(1e-6)
  yield
  sys.setswitchinterval(previous)


@pytest.fixture
def writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PackageWriter:
  """Write throwaway packages under ``tmp_path``, on a ``sys.path`` entry undone after the test."""
  return PackageWriter(tmp_path=tmp_path, monkeypatch=monkeypatch)
