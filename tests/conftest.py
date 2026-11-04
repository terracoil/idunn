"""Shared fixtures: one process-wide singleton, wiped clean around every test, and a fast switch."""

import sys
from collections.abc import Iterator

import pytest
from idunn import Idunn


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
