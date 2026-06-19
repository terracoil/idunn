"""Ports for the orchard example (discovered because the module is named ``ports``)."""

from typing import Protocol

from idunn import Port


@Port
class AppleBasketPort(Protocol):
  """Source of apples that keep the gods young."""

  def take_apple(self) -> str:
    """Return an apple from the basket."""
    ...
