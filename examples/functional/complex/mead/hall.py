"""The library's public entry point, a function like everything else here."""

from typing import Final

from idunn import Idunn

from .cupbearer import pour_for

ROOT: Final[str] = 'examples.functional.complex.mead'  # plain 'mead' if it shipped on its own


def pour(guest: str) -> str:
  """Pour for ``guest``, wiring the library first if nobody has yet.
  A library is imported, not started, so it has no startup hook to discover from. Each entry point
  bootstraps the library's own root instead: the first call discovers, later calls are a cache hit.
  """
  Idunn().bootstrap(ROOT)
  return pour_for(guest)
