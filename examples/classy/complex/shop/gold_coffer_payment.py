"""The ``prod`` payment adapter."""

from idunn import Adapter

from .ports import PaymentPort


@Adapter(PaymentPort, envs='prod')
class GoldCofferPayment(PaymentPort):
  """Takes real gold. Its ``envs`` never overlap the rune stick's, so an unkeyed resolve never has
  two answers to choose between, and the consumer never learns which environment it is in.
  """

  def charge(self, customer: str, amount: int) -> str:
    """Collect ``amount`` marks from ``customer``."""
    return f"{customer} pays {amount} marks in Andvari's gold, curse included"
