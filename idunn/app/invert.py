"""The @Invert decorator."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Mapping
from typing import Any, get_type_hints

from idunn.internal import DecoratorSupport

from .idunn import Idunn

Init = Callable[..., None]


class Invert:
  """Auto-inject registered adapters for ``@Port``-typed constructor parameters.

  Applied with parentheses (``@Invert()``) to a constructor. Every parameter whose type
  hint is a ``@Port`` is resolved from the process-wide :class:`Idunn` container when the
  constructor runs and assigned to ``self.<name>`` (the body may override; a caller-supplied
  argument always wins). Constructing the decorated object is the sanctioned way to start an
  object graph — there is no public ``resolve``.

  A parameter typed ``Port | None`` (or any ``@Port`` parameter with a default) is
  *optional*: if no adapter is active it falls back to the default / ``None`` instead of
  raising. Pick a *keyed* adapter with ``keys={'param': 'name'}``, choosing right at the
  point of use.

  Forms::

    @Invert()                              # infer ports from the type hints
    @Invert(keys={'basket': 'golden'})     # pick keyed adapters
    @Invert({'basket': AppleBasketPort})   # explicit param -> port (no annotation)
  """

  __slots__ = ('_explicit_ports', '_keys')

  def __call__(self, init: Init) -> Init:
    """Wrap ``init`` so its ``@Port``-typed parameters are injected at construction time."""
    signature = inspect.signature(init)
    discovered, optional_names = DecoratorSupport.extract_port_parameters(get_type_hints(init))
    port_params: dict[str, type[Any]] = {**self._explicit_ports, **discovered}

    @functools.wraps(init)
    def wrapper(instance: Any, *args: Any, **kwargs: Any) -> None:
      supplied = signature.bind_partial(instance, *args, **kwargs).arguments
      for name, port in port_params.items():
        if name not in supplied:  # a caller-supplied argument always wins
          kwargs[name] = self._inject(
            name=name,
            port=port,
            parameter=signature.parameters[name],
            optional=name in optional_names,
          )
        setattr(instance, name, kwargs[name] if name in kwargs else supplied[name])
      init(instance, *args, **kwargs)

    return wrapper

  def __init__(
    self,
    ports: Mapping[str, type[Any]] | None = None,
    *,
    keys: Mapping[str, str] | None = None,
  ) -> None:
    """Capture explicit ``param -> port`` overrides and per-parameter adapter keys."""
    if callable(ports) and not isinstance(ports, Mapping):
      message = '@Invert must be applied with parentheses: use @Invert() or @Invert(keys=...)'
      raise TypeError(message)
    self._explicit_ports: dict[str, type[Any]] = dict(ports) if ports is not None else {}
    self._keys: dict[str, str] = dict(keys) if keys is not None else {}

  def _inject(
    self,
    *,
    name: str,
    port: type[Any],
    parameter: inspect.Parameter,
    optional: bool,
  ) -> Any:
    """Resolve one parameter: the active adapter, or the default / ``None`` when optional."""
    container = Idunn()
    key = self._keys.get(name)
    has_default = parameter.default is not inspect.Parameter.empty
    absent = (optional or has_default) and not container._has(port, key)
    result: Any
    if absent:
      result = parameter.default if has_default else None
    else:
      result = container._inject(port, key)
    return result
