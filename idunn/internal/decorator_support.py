"""Support helpers shared by the Idunn decorators."""

from collections.abc import Iterable, Mapping
from typing import Any, get_args

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

  @staticmethod
  def port_from_annotation(annotation: Any) -> tuple[type[Any] | None, bool]:
    """Resolve a constructor annotation to ``(port, optional)``.

    A bare ``@Port`` annotation yields ``(port, False)``; an ``Optional`` port
    (``Port | None``) yields ``(port, True)`` — the ``| None`` is the signal that a
    missing adapter is tolerable. Anything else yields ``(None, False)``.
    """
    args = get_args(annotation)
    non_none = tuple(arg for arg in args if arg is not type(None))
    result: tuple[type[Any] | None, bool]
    if getattr(annotation, '__idunn_port__', False):
      result = (annotation, False)
    elif (
      type(None) in args and len(non_none) == 1 and getattr(non_none[0], '__idunn_port__', False)
    ):
      result = (non_none[0], True)
    else:
      result = (None, False)
    return result

  @staticmethod
  def extract_port_parameters(
    hints: Mapping[str, Any],
  ) -> tuple[dict[str, type[Any]], set[str]]:
    """Split a ``name -> annotation`` mapping into ``(ports, optional_names)``.

    ``ports`` maps each ``@Port``-typed parameter name to its port; ``optional_names``
    holds the subset whose annotation is ``Port | None``. The synthetic ``'return'``
    key and every non-port annotation are skipped.
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
