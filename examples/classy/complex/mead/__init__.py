"""A small library that wires itself: import ``MeadHall`` and pour; nobody has to discover it.
It lives inside the example to keep the repo tidy, but behaves as if it shipped separately: the
shop never discovers it, and it never asks the shop for anything.
"""

from .hall import MeadHall

__all__ = ['MeadHall']
