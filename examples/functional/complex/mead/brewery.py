"""The library's one adapter."""

from idunn import Adapter

from .ports import BrewPort


@Adapter(BrewPort)
class KvasirBrewery(BrewPort):
  """Brews the mead of poetry, to a recipe best not asked about."""

  def draw(self) -> str:
    """Draw a cup."""
    return 'the mead of poetry'
