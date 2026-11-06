"""A read-only view of the storeroom, deliberately not a port."""

from typing import Protocol


class StockView(Protocol):
  """What a stocktaker needs from a storeroom: the count, and no way to change it.
  A plain Protocol, so ``@Invert`` cannot infer a port from it; an explicit map names the port
  that fills it, and the type checker keeps the consumer's hands off ``take``.
  """

  def remaining(self) -> int:
    """Return how many apples are left."""
    ...
