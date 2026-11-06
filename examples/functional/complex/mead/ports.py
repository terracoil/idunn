"""The library's one port."""

from typing import Protocol

from idunn import Port


@Port
class BrewPort(Protocol):
  """Something to drink."""

  def draw(self) -> str:
    """Return one cup's worth."""
    ...
