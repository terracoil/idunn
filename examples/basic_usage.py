"""Minimal Idunn example: decorate, bootstrap once, then just construct."""

from typing import Protocol

from idunn import Adapter, Idunn, Invert, LifecycleEnum, Port


@Port
class AppleBasketPort(Protocol):
  """Source of apples that keep the gods young."""

  def take_apple(self) -> str:
    """Return an apple from the basket."""
    ...


@Adapter(AppleBasketPort, lifecycle=LifecycleEnum.SINGLETON)
class GoldenAppleBasketAdapter(AppleBasketPort):
  """Basket of golden apples shared as a singleton."""

  def take_apple(self) -> str:
    """Hand out a golden apple."""
    return '🍎 youth restored'


class Feast:
  """A feast whose apple basket is injected automatically by @Invert."""

  basket: AppleBasketPort  # assigned by @Invert at construction time

  @Invert
  def __init__(self, basket: AppleBasketPort, other: str) -> None:
    """Keep ``other``; ``self.basket`` is injected and assigned for us."""
    self.other = other

  def serve(self) -> str:
    """Serve the feast using the injected basket."""
    return f'Asgard feast ({self.other}): {self.basket.take_apple()}'


if __name__ == '__main__':
  Idunn().register_adapter(GoldenAppleBasketAdapter)  # one-time bootstrap
  feast = Feast(other='funky')
  print(feast.serve())
