"""The library's internal consumer."""

from idunn import Invert

from .ports import BrewPort


class Cupbearer:
  """Pours for guests. Internal: callers reach it through ``MeadHall``, which wires it first."""

  brewery: BrewPort  # assigned by @Invert

  @Invert()
  def __init__(self, *, brewery: BrewPort) -> None:
    """Nothing to do: the brewery is assigned before this body runs."""

  def pour(self, guest: str) -> str:
    """Serve ``guest`` and note the side effects."""
    return f'{guest} drinks {self.brewery.draw()} and speaks only in verse'
