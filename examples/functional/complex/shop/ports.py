"""The shop's ports, five to a module on purpose: each is a contract of a line or two, and five
files that short would be ceremony rather than clarity. Discovery does not mind either way.
"""

from typing import Protocol

from idunn import Port


@Port
class StoreroomPort(Protocol):
  """Where the golden apples wait between sales."""

  def take(self, count: int) -> int:
    """Remove ``count`` apples and return how many are left."""
    ...

  def remaining(self) -> int:
    """Return how many apples are left, without touching any."""
    ...


@Port
class PaymentPort(Protocol):
  """How a customer settles up, which depends on who is watching the till."""

  def charge(self, customer: str, amount: int) -> str:
    """Take ``amount`` marks from ``customer`` and return the receipt."""
    ...


@Port
class HeraldPort(Protocol):
  """Carries news. Every herald is keyed, so nobody gets one without asking for it by name."""

  def announce(self, news: str) -> str:
    """Return ``news`` as the herald delivers it."""
    ...


@Port
class SagaPort(Protocol):
  """Turns deeds into verse. Optional: the shop trades just as well unsung."""

  def tell(self, deed: str) -> str:
    """Return the verse for ``deed``."""
    ...


@Port
class CheckoutPort(Protocol):
  """Rings up a sale: stock out, money in, receipt back."""

  def sell(self, customer: str, count: int) -> str:
    """Sell ``count`` apples to ``customer`` and return the receipt."""
    ...
