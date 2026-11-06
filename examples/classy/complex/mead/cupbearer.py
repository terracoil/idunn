"""The library's internal consumer, and the one place the library wires itself."""

from typing import Final

from idunn import Invert

from .ports import BrewPort


class Cupbearer:
  """Pours for guests. Internal: callers reach it through ``MeadHall``.
  A library is imported, not started, so it has no startup hook to discover from. ``bootstrap=``
  names the library's own root instead: the first cupbearer hired discovers it, later ones are a
  cache hit, and one handed a brewery by hand (in a test, say) discovers nothing at all.
  """

  ROOT: Final[str] = 'examples.classy.complex.mead'  # plain 'mead' if it shipped on its own

  brewery: BrewPort  # assigned by @Invert

  @Invert(bootstrap=ROOT)
  def __init__(self, *, brewery: BrewPort) -> None:
    """Nothing to do: the library is wired and the brewery assigned before this body runs."""

  def pour(self, guest: str) -> str:
    """Serve ``guest`` and note the side effects."""
    return f'{guest} drinks {self.brewery.draw()} and speaks only in verse'
