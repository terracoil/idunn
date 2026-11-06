"""The storeroom adapter: the one piece of state in the shop."""

from idunn import Adapter, LifecycleEnum

from .ports import StoreroomPort


@Adapter(StoreroomPort, lifecycle=LifecycleEnum.SINGLETON)
class Storeroom(StoreroomPort):
  """Six golden apples and a memory. A ``SINGLETON``, so every till sells from the same shelf;
  a ``TRANSIENT`` storeroom would restock itself for each customer, which is generous but brief.
  """

  def __init__(self) -> None:
    """Stock the shelf. Idunn's orchard is magic; her storeroom, regrettably, is not."""
    self._apples: int = 6

  def take(self, count: int) -> int:
    """Remove ``count`` apples, refusing to sell what is not there, and return what is left."""
    if count > self._apples:
      raise ValueError(f'only {self._apples} apples left, and {count} were asked for')
    self._apples -= count
    return self._apples

  def remaining(self) -> int:
    """Count the apples."""
    return self._apples
