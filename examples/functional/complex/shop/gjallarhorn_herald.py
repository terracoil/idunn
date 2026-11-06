"""The loud herald."""

from idunn import Adapter

from .ports import HeraldPort


@Adapter(HeraldPort, key='horn')
class GjallarhornHerald(HeraldPort):
  """Heimdall's horn, for news meant for all nine worlds. Keyed too: nobody wants it by default."""

  def announce(self, news: str) -> str:
    """Blare ``news``."""
    return f'Gjallarhorn blares: {news}'
