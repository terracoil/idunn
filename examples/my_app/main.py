"""Entry point for ``my_app``: discover once, then just construct.

Run from the repo root with ``poetry run python -m examples.my_app.main``. The discovery root is
``'examples.my_app'`` because here ``my_app`` lives inside the ``examples`` package; in your own
project it is just ``'my_app'``.
"""

from idunn import Idunn, Invert

from .ports import AppleBasketPort


class Feast:
  """An ``@Invert`` root: its basket is injected when it is constructed."""

  basket: AppleBasketPort  # declared for the type checker; @Invert assigns it

  @Invert()
  def __init__(self, basket: AppleBasketPort, host: str) -> None:
    """Keep ``host``; ``self.basket`` is injected and assigned for you."""
    self.host = host

  def serve(self) -> str:
    """Serve the feast with an apple from the injected basket."""
    return f'{self.host}: {self.basket.take_apple()}'


if __name__ == '__main__':
  Idunn().autodiscover('examples.my_app')
  print(Feast(host='Bragi').serve())  # Bragi: youth restored
