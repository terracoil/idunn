"""Ports for the simple example. The module name is a courtesy to readers, not a discovery rule."""

from typing import Protocol

from idunn import Port


@Port
class AppleBasketPort(Protocol):
  """Source of apples that keep the gods young."""

  def take_apple(self) -> str:
    """Return an apple from the basket."""
    ...
