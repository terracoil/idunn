"""What ``@Adapter`` captured, frozen at decoration time."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .lifecycle_enum import LifecycleEnum


@dataclass(frozen=True, slots=True)
class AdapterDeclaration:
  """The options handed to ``@Adapter``, frozen so nobody edits the label after the fact.
  Kept apart from :class:`AdapterMetadata` because it exists before registration does: it is made
  when the decorator is constructed, before it has seen the class it will label, and long before
  anyone knows the registration order. It travels on the class as ``__idunn_adapter__``, and the
  stamp counts only in the class's own ``__dict__``: a subclass inherits the attribute, never the
  badge, so discovery and ``Harness.install`` agree on who is an adapter by asking :meth:`of`.
  """

  ATTRIBUTE: ClassVar[str] = '__idunn_adapter__'

  port: type[Any]
  key: str | None
  lifecycle: LifecycleEnum
  envs: frozenset[str] | None

  def attach(self, cls: type[Any]) -> None:
    """Stamp this declaration on ``cls``, where :meth:`of` (and nothing inherited) will find it."""
    setattr(cls, self.ATTRIBUTE, self)

  @classmethod
  def of(cls, target: object) -> AdapterDeclaration | None:
    """Return the declaration stamped on ``target`` itself, or ``None`` if it never wore one.
    Reads ``target``'s own ``__dict__``, not the attribute: an undecorated subclass of an adapter
    would otherwise borrow its parent's badge and be registered under the parent's port and key.
    """
    found: object = getattr(target, '__dict__', {}).get(cls.ATTRIBUTE)
    return found if isinstance(found, cls) else None
