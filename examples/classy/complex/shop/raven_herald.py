"""The quiet herald."""

from idunn import Adapter

from .ports import HeraldPort


@Adapter(HeraldPort, key='raven')
class RavenHerald(HeraldPort):
  """Odin's raven, for news meant for one ear. Keyed, so only a parameter that names it gets it."""

  def announce(self, news: str) -> str:
    """Whisper ``news``."""
    return f'Huginn whispers: {news}'
