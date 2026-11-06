"""The stall, as two functions: no instance to hold the ports, so each call is handed its own."""

from idunn import Invert

from .ports import CheckoutPort, HeraldPort, SagaPort


@Invert(keys={'crier': 'horn'})
def open_stall(keeper: str, *, crier: HeraldPort) -> str:
  """Announce the opening, loudly: ``crier`` names the keyed horn, so the raven stays home."""
  return crier.announce(f"{keeper}'s stall is open")


@Invert()
def sell(customer: str, count: int, *, till: CheckoutPort, saga: SagaPort | None = None) -> str:
  """Sell through a till, with a verse when there is a skald to sing it.
  ``saga`` is optional, so it is ``None`` wherever no skald is active rather than an error.
  """
  receipt: str = till.sell(customer, count)
  deed: str = f'{customer} bought {count} golden apples'
  return receipt if saga is None else f'{receipt}\n{saga.tell(deed)}'
