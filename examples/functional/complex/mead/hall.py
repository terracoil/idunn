"""The library's public entry point, a function like everything else here."""

from .cupbearer import pour_for


def pour(guest: str) -> str:
  """Pour for ``guest``. No wiring here: ``pour_for`` wears ``@Invert(bootstrap=...)``."""
  return pour_for(guest)
