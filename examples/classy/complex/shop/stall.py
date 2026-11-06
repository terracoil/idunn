"""The stall, the shop's front-of-house consumer."""

from idunn import Invert

from .ports import CheckoutPort, HeraldPort, SagaPort


class Stall:
  """Idunn's stall: opens by horn, sells through a till, and is sung about when a skald is near.
  It asks for all three and builds none of them, which is the whole trick.
  """

  till: CheckoutPort  # every port parameter is assigned by @Invert
  crier: HeraldPort
  saga: SagaPort | None

  @Invert(keys={'crier': 'horn'})
  def __init__(
    self,
    keeper: str,
    *,
    till: CheckoutPort,
    crier: HeraldPort,
    saga: SagaPort | None = None,
  ) -> None:
    """Keep ``keeper``. The ports sit after ``*``: ``crier`` takes the keyed horn, and ``saga`` is
    optional, so it is ``None`` wherever no skald is active rather than an error.
    """
    self.keeper: str = keeper

  def open(self) -> str:
    """Announce the opening, loudly."""
    return self.crier.announce(f"{self.keeper}'s stall is open")

  def sell(self, customer: str, count: int) -> str:
    """Sell through the till, with a verse when there is a skald to sing it."""
    receipt: str = self.till.sell(customer, count)
    deed: str = f'{customer} bought {count} golden apples'
    return receipt if self.saga is None else f'{receipt}\n{self.saga.tell(deed)}'
