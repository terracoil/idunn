"""One injectable port parameter, worked out once and reused for every build."""

from __future__ import annotations

from dataclasses import dataclass
from inspect import Parameter
from typing import Any


@dataclass(frozen=True, slots=True)
class ParameterPlan:
  """Everything Idunn needs to fill one port parameter, minus the adapter itself.
  Built from the type hints and the ``@Invert`` declaration the first time they are needed, then
  reused, so the hot path never touches ``inspect`` again. ``@Invert`` consumers and adapter
  constructors share one plan shape, which is how they share one set of rules.
  """

  name: str
  port: type[Any]
  key: str | None  # only ever from @Invert(keys=...)
  optional: bool  # annotated `Port | None`
  default: Any = Parameter.empty  # Parameter.empty when there is none, since None is a value

  @property
  def fallback(self) -> Any:
    """What a tolerant parameter gets when no adapter is active: its default, else ``None``."""
    return None if self.default is Parameter.empty else self.default

  @property
  def tolerant(self) -> bool:
    """Whether a missing adapter is survivable: optional, or there is a default to fall back on."""
    return self.optional or self.default is not Parameter.empty
