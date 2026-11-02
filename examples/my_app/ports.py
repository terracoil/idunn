"""Ports for ``my_app``; ``ports`` is a naming convention, not a discovery requirement."""

from typing import Protocol

from idunn import Port


@Port
class AppleBasketPort(Protocol):
  """Source of apples that keep the gods young."""

  def take_apple(self) -> str:
    """Return an apple from the basket."""
    ...
