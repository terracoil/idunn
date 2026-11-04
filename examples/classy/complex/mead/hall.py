"""The library's public entry point."""

from typing import Final

from idunn import Idunn

from .cupbearer import Cupbearer


class MeadHall:
  """The front door, and the only name the library exports.
  A library is imported, not started, so it has no startup hook to discover from. Each entry point
  bootstraps the library's own root instead: the first call discovers, later calls are a cache hit.
  """

  ROOT: Final[str] = 'examples.classy.complex.mead'  # plain 'mead' if it shipped on its own

  def __init__(self) -> None:
    """Wire the library on first use, then hire a cupbearer from the freshly wired graph."""
    Idunn().bootstrap(self.ROOT)
    self._cupbearer: Cupbearer = Cupbearer()

  def pour(self, guest: str) -> str:
    """Pour for ``guest``."""
    return self._cupbearer.pour(guest)
