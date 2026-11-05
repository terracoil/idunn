"""A function's port plan, made now if its type hints resolve and on first call if they do not."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from typing import Any

from idunn.domain import FunctionShape, InvertDeclaration, ParameterPlan

from .constructor_planner import ConstructorPlanner


class LazyPlan:
  """Holds one ``@Invert`` function's plan, planning eagerly when it can and lazily when it must.
  At decoration a hint may name a class defined further down the module (or the class being
  defined, as in ``Node | None``), which raises ``NameError`` until the module finishes. So
  :meth:`try_now` plans and swallows exactly that, and :meth:`get` retries on first call, when the
  name exists. Every other error, an annotation rule broken included, still surfaces at decoration.
  It lives in the wrapper's closure, one per decorated function, because one ``Invert(...)`` can
  decorate several. Two threads racing the first :meth:`get` build identical plans; one wins.
  """

  __slots__ = ('_declaration', '_function', '_plan', '_shape')

  def __init__(
    self,
    function: Callable[..., Any],
    *,
    shape: FunctionShape,
    declaration: InvertDeclaration,
  ) -> None:
    """Remember what to plan; nothing is planned until :meth:`try_now` or :meth:`get`."""
    self._function: Callable[..., Any] = function
    self._shape: FunctionShape = shape
    self._declaration: InvertDeclaration = declaration
    self._plan: tuple[ParameterPlan, ...] | None = None

  def get(self) -> tuple[ParameterPlan, ...]:
    """Return the plan, making it on first use. A failure is not cached; the next call retries."""
    plan: tuple[ParameterPlan, ...] | None = self._plan
    if plan is None:
      plan = ConstructorPlanner.plan(
        self._function, shape=self._shape, declaration=self._declaration
      )
      self._plan = plan
    return plan

  @property
  def ready(self) -> bool:
    """Whether the plan exists yet; ``False`` only while a forward reference holds it up."""
    return self._plan is not None

  def try_now(self) -> bool:
    """Plan at once unless a hint is still a forward reference; return whether it worked."""
    with suppress(NameError):
      self.get()
    return self.ready
