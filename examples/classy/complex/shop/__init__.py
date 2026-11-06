"""The shop application: ports, adapters and the two consumers ``main`` builds."""

from .stall import Stall
from .stocktaker import Stocktaker

__all__ = ['Stall', 'Stocktaker']
