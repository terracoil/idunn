"""The stocktaker, who counts and never sells."""

from idunn import Invert

from .ports import HeraldPort, StoreroomPort
from .stock_view import StockView


class Stocktaker:
  """Counts the apples and sends the tally by raven.
  It only reads, so it asks for the narrow ``StockView``; that is not a port, so the explicit map
  says ``StoreroomPort`` fills it, and the type checker keeps ``take`` out of reach.
  """

  stock: StockView  # both assigned by @Invert
  messenger: HeraldPort

  @Invert({'stock': StoreroomPort}, keys={'messenger': 'raven'})
  def __init__(self, *, stock: StockView, messenger: HeraldPort) -> None:
    """Nothing left to do: both parameters are assigned before this body runs."""

  def report(self) -> str:
    """Send the count, quietly."""
    return self.messenger.announce(f'{self.stock.remaining()} golden apples left')
