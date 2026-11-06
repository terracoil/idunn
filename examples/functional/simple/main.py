"""Entry point: discover once, then just call things.
The same wiring as ``examples.classy.simple`` without the class: ``feast`` is the whole consumer.
Discovery imports this module too, so the work stays under the ``__main__`` guard.
"""

from idunn import Idunn, Invert

from .ports import AppleBasketPort


@Invert()
def feast(host: str, *, basket: AppleBasketPort) -> str:
  """Serve the feast. ``basket`` is resolved at each call; pass one yourself and that one wins."""
  return f'{host}: {basket.take_apple()}'


if __name__ == '__main__':
  Idunn().autodiscover('examples.functional.simple')
  print(feast('Bragi'))  # Bragi: youth restored
