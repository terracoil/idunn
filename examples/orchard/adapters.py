"""Adapters for the orchard example (discovered because the module is named ``adapters``)."""

from idunn import Adapter, LifecycleEnum

from .ports import AppleBasketPort


@Adapter(AppleBasketPort, lifecycle=LifecycleEnum.SINGLETON)
class GoldenAppleBasketAdapter(AppleBasketPort):
  """Unkeyed basket of golden apples — answers a plain ``@Invert``."""

  def take_apple(self) -> str:
    """Hand out a golden apple."""
    return '🍎 youth restored'


@Adapter(AppleBasketPort, key='wild')
class WildAppleBasketAdapter(AppleBasketPort):
  """Keyed basket — opt-in, only reached via ``@Invert(keys=...)``."""

  def take_apple(self) -> str:
    """Hand out a wild apple."""
    return '🍏 a tart wild apple'
