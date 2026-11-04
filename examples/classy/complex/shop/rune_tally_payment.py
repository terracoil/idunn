"""The ``local`` payment adapter."""

from idunn import Adapter

from .ports import PaymentPort


@Adapter(PaymentPort, envs='local')
class RuneTallyPayment(PaymentPort):
  """Scratches the debt on a rune stick. Fine for a developer's laptop, where nobody pays anyway."""

  def charge(self, customer: str, amount: int) -> str:
    """Record what ``customer`` owes and collect nothing."""
    return f'{customer} owes {amount} marks, scratched on a rune stick'
