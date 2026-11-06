"""The library's internal consumer, as a function, and the one place the library wires itself."""

from typing import Final

from idunn import Invert

from .ports import BrewPort

ROOT: Final[str] = 'examples.functional.complex.mead'  # plain 'mead' if it shipped on its own


@Invert(bootstrap=ROOT)
def pour_for(guest: str, *, brewery: BrewPort) -> str:
  """Serve ``guest`` and note the side effects. Internal: callers go through ``pour``.
  A library is imported, not started, so it has no startup hook to discover from. ``bootstrap=``
  names the library's own root instead: the first call discovers it, later calls are a cache hit,
  and a call handed a brewery by hand (in a test, say) discovers nothing at all.
  """
  return f'{guest} drinks {brewery.draw()} and speaks only in verse'
