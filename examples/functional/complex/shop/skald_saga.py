"""The optional saga adapter."""

from idunn import Adapter

from .ports import SagaPort


@Adapter(SagaPort, envs='local')
class SkaldSaga(SagaPort):
  """A skald who sings of every sale. Only ``local`` can afford one; ``prod`` sells unsung, and
  ``SagaPort | None`` consumers get ``None`` there instead of an ``AdapterNotFoundError``.
  """

  def tell(self, deed: str) -> str:
    """Put ``deed`` into verse, loosely."""
    return f'  (the skald sings of how {deed})'
