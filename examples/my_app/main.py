"""Entry point for ``my_app``: discover once, then just construct things.
Run from the repo root with ``poetry run python -m examples.my_app.main``. The discovery root is
``'examples.my_app'`` because here ``my_app`` lives inside the ``examples`` package; in your own
project it is plain ``'my_app'``. Discovery imports every module under the root, this one
included, so the actual work hides under the ``__main__`` guard. Run with ``-m``, the copy you are
running is reused rather than imported a second time.
"""

from idunn import Idunn, Invert

from .ports import AppleBasketPort


class Feast:
  """An ``@Invert()`` root: its basket arrives when it is constructed.
  The port sits after ``*``, keyword-only, so ``Feast('Bragi')`` can only mean the host.
  """

  basket: AppleBasketPort  # declared for the type checker; @Invert assigns it

  @Invert()
  def __init__(self, host: str, *, basket: AppleBasketPort) -> None:
    """Keep ``host``; ``self.basket`` is already injected and assigned by the time this runs."""
    self.host = host

  def serve(self) -> str:
    """Serve the feast with an apple from the injected basket."""
    return f'{self.host}: {self.basket.take_apple()}'


if __name__ == '__main__':
  Idunn().autodiscover('examples.my_app')
  print(Feast('Bragi').serve())  # Bragi: youth restored
