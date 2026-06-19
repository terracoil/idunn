"""Minimal Idunn example: decorate, discover once, then just construct.

Run from the repo root with::

    poetry run python -m examples.basic_usage

The container is touched exactly once — ``Idunn().autodiscover(...)`` at startup.
After that, normal code constructs ``Feast`` / ``Picnic`` and ``@Invert`` wires the
apple basket in automatically; no ``resolve()``, no ``Idunn`` in application code.
"""

from idunn import Idunn, Invert

from .orchard.ports import AppleBasketPort


class Feast:
  """An @Invert-root: its unkeyed basket is injected at construction time."""

  basket: AppleBasketPort  # assigned by @Invert

  @Invert
  def __init__(self, basket: AppleBasketPort, other: str) -> None:
    """Keep ``other``; ``self.basket`` is injected and assigned for us."""
    self.other = other

  def serve(self) -> str:
    """Serve the feast using the injected (unkeyed) basket."""
    return f'Asgard feast ({self.other}): {self.basket.take_apple()}'


class Picnic:
  """An @Invert-root that opts into the keyed 'wild' basket at the point of use."""

  basket: AppleBasketPort  # assigned by @Invert

  @Invert(keys={'basket': 'wild'})
  def __init__(self, basket: AppleBasketPort) -> None:
    """``self.basket`` is the keyed adapter chosen by ``keys=``."""

  def serve(self) -> str:
    """Serve the picnic using the injected (keyed) basket."""
    return f'Midgard picnic: {self.basket.take_apple()}'


class Example:
  """Bundles the example so there are no loose module-level functions."""

  @staticmethod
  def main() -> None:
    """Discover the orchard, then let @Invert wire each consumer."""
    Idunn().autodiscover('examples.orchard')
    print(Feast(other='funky').serve())  # plain @Invert -> unkeyed golden basket
    print(Picnic().serve())  # @Invert(keys=...) -> keyed wild basket


if __name__ == '__main__':
  Example.main()
