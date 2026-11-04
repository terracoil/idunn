"""The checkout adapter, which needs two other ports to do its job."""

from typing import Final

from idunn import Adapter

from .ports import CheckoutPort, PaymentPort, StoreroomPort


@Adapter(CheckoutPort)
class Till(CheckoutPort):
  """Rings up sales. ``TRANSIENT``, so each resolve builds a fresh till, and every till is handed
  the one shared storeroom and whichever payment the environment allows.
  """

  PRICE: Final[int] = 3  # marks per golden apple; eternal youth is underpriced

  def __init__(self, *, storeroom: StoreroomPort, payment: PaymentPort) -> None:
    """Undecorated: the resolver passes every port by keyword, so plain parameters are enough."""
    self._storeroom: StoreroomPort = storeroom
    self._payment: PaymentPort = payment

  def sell(self, customer: str, count: int) -> str:
    """Take the apples first, then the money: charging for apples that do not exist ends badly."""
    left: int = self._storeroom.take(count)
    return f'{self._payment.charge(customer, count * self.PRICE)}; {left} left'
