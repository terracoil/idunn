"""The shop application: ports, adapters and the three functions ``main`` calls."""

from .stall import open_stall, sell
from .stocktaker import take_stock

__all__ = ['open_stall', 'sell', 'take_stock']
