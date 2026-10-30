"""Adapters for ``my_app`` (discovered because the module is named ``adapters``)."""

from idunn import Adapter, LifecycleEnum

from .ports import AppleBasketPort


@Adapter(AppleBasketPort, lifecycle=LifecycleEnum.SINGLETON)
class GoldenAppleBasketAdapter(AppleBasketPort):
  """The one basket ``AppleBasketPort`` resolves to, built once and reused."""

  def take_apple(self) -> str:
    """Hand out a golden apple."""
    return 'youth restored'
