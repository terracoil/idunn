"""The library's internal consumer, as a function."""

from idunn import Invert

from .ports import BrewPort


@Invert()
def pour_for(guest: str, *, brewery: BrewPort) -> str:
  """Serve ``guest`` and note the side effects. Internal: callers go through ``pour``."""
  return f'{guest} drinks {brewery.draw()} and speaks only in verse'
