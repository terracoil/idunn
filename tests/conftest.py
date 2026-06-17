"""Shared fixtures: isolate the process-wide Idunn singleton per test."""

from collections.abc import Iterator

import pytest
from idunn import Idunn


@pytest.fixture(autouse=True)
def _reset_idunn() -> Iterator[None]:
  """Give every test a clean singleton bound to a deterministic environment."""
  Idunn().reset(environment='local')
  yield
  Idunn().reset(environment='local')
