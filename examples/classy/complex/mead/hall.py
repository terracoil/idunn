"""The library's public entry point."""

from .cupbearer import Cupbearer


class MeadHall:
  """The front door, and the only name the library exports.
  It wires nothing itself: the ``Cupbearer`` it hires wears ``@Invert(bootstrap=...)``, so the
  library wires itself the first time anyone pours, and a second hall is a cache hit.
  """

  def __init__(self) -> None:
    """Hire a cupbearer; the first one hired wires the library on the way in."""
    self._cupbearer: Cupbearer = Cupbearer()

  def pour(self, guest: str) -> str:
    """Pour for ``guest``."""
    return self._cupbearer.pour(guest)
