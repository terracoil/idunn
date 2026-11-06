"""The stocktaker, as a function that counts and never sells."""

from idunn import Invert

from .ports import HeraldPort, StoreroomPort
from .stock_view import StockView


@Invert({'stock': StoreroomPort}, keys={'messenger': 'raven'})
def take_stock(*, stock: StockView, messenger: HeraldPort) -> str:
  """Count the apples and send the tally by raven.
  It only reads, so it asks for the narrow ``StockView``; that is not a port, so the explicit map
  says ``StoreroomPort`` fills it, and the type checker keeps ``take`` out of reach.
  """
  return messenger.announce(f'{stock.remaining()} golden apples left')
