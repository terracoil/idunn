"""Adapters for ``my_app``, kept beside ``ports`` for the humans; Idunn would find them anywhere."""

from idunn import Adapter, LifecycleEnum

from .ports import AppleBasketPort


@Adapter(AppleBasketPort, lifecycle=LifecycleEnum.SINGLETON)
class GoldenAppleBasketAdapter(AppleBasketPort):
  """The one basket ``AppleBasketPort`` resolves to, built once and shared by everyone."""

  def take_apple(self) -> str:
    """Hand out a golden apple."""
    return 'youth restored'
