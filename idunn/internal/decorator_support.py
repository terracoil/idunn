"""Support helpers shared by the Idunn decorators."""

from collections.abc import Iterable

from idunn.util import Environment


class DecoratorSupport:
  """Support logic for decorator functions."""

  @staticmethod
  def normalize_envs(envs: Iterable[str] | str | None) -> frozenset[str] | None:
    """Normalize decorator environment names."""
    if envs is None:
      return None
    raw_vals: Iterable[str] = (envs,) if isinstance(envs, str) else envs
    return frozenset(Environment.normalize(item) for item in raw_vals)
