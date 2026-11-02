"""Shared fixtures: one process-wide singleton, wiped clean around every test."""

from collections.abc import Iterator

import pytest
from idunn import Idunn


@pytest.fixture(autouse=True)
def _reset_idunn() -> Iterator[None]:
  """Give every test a clean singleton bound to a deterministic environment."""
  Idunn().reset(environment='local')
  yield
  Idunn().reset(environment='local')
