"""Annotation and environment helpers shared by the decorators and the resolver."""

from collections.abc import Iterable, Mapping
from typing import Any, get_args

from idunn.util import Environment

from .port_registry import PortRegistry


class DecoratorSupport:
  """Helpers shared by the decorators and the resolver.
  One copy of the annotation rules means ``@Invert()`` consumers and adapter constructors cannot
  drift apart on what counts as an optional port.
  """

  @staticmethod
  def extract_port_parameters(
    hints: Mapping[str, Any],
  ) -> tuple[dict[str, type[Any]], set[str]]:
    """Split a ``name -> annotation`` mapping into ``(ports, optional_names)`` for ``@Invert()``.
    ``ports`` maps each ``@Port``-typed parameter name to its port; ``optional_names`` holds the
    subset annotated ``Port | None``. The synthetic ``'return'`` key and every non-port
    annotation are skipped.
    """
    ports: dict[str, type[Any]] = {}
    optional_names: set[str] = set()
    for name, annotation in hints.items():
      port, is_optional = DecoratorSupport.port_from_annotation(annotation)
      if name != 'return' and port is not None:
        ports[name] = port
        if is_optional:
          optional_names.add(name)
    return (ports, optional_names)

  @staticmethod
  def normalize_envs(envs: Iterable[str] | str | None) -> frozenset[str] | None:
    """Normalize ``envs`` to a frozenset of names, or ``None`` for "everywhere".

    Done at decoration, so the names already compare equal to what ``Environment.current``
    produces. An empty collection yields an empty set: an adapter that is active nowhere, which
    is legal if not especially useful.
    """
    if envs is None:
      return None
    raw_vals: Iterable[str] = (envs,) if isinstance(envs, str) else envs
    return frozenset(Environment.normalize(item) for item in raw_vals)

  @staticmethod
  def port_from_annotation(annotation: Any) -> tuple[type[Any] | None, bool]:
    """Resolve a constructor annotation to ``(port, optional)``.
    A bare ``@Port`` annotation yields ``(port, False)``; ``Port | None`` yields ``(port, True)``,
    the ``| None`` being the signal that a missing adapter is survivable. Anything else yields
    ``(None, False)``.
    """
    args = get_args(annotation)
    non_none = tuple(arg for arg in args if arg is not type(None))
    result: tuple[type[Any] | None, bool]
    if PortRegistry.is_port(annotation):
      result = (annotation, False)
    elif type(None) in args and len(non_none) == 1 and PortRegistry.is_port(non_none[0]):
      result = (non_none[0], True)
    else:
      result = (None, False)
    return result
