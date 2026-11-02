"""The ``@Invert`` decorator: where an object graph actually gets built."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Mapping
from typing import Any, get_type_hints

from idunn.internal import DecoratorSupport
from idunn.util import QualifiedName

from .idunn import Idunn

Init = Callable[..., None]


class Invert:
  """Inject registered adapters into a constructor's ``@Port``-typed parameters.
  Applied with parentheses (``@Invert()``) to an ``__init__``. When the constructor runs, every
  port parameter the caller left out is resolved from the :class:`Idunn` container, and every
  port parameter, injected or supplied, is assigned to ``self.<name>`` before the body runs. A
  caller-supplied argument always wins, which is what keeps consumers testable without the
  container. Building an ``@Invert()`` object is the only way to start a graph; there is no
  public ``resolve``, so wiring code has nowhere to leak into business logic.

  A parameter typed ``Port | None``, or any port parameter with a default, is *optional*: with no
  active adapter it gets the default or ``None`` instead of an exception. ``keys`` picks a keyed
  adapter per parameter, right where the choice matters.

  Two things that surprise people. Pass plain arguments by keyword: a positional argument fills
  the next parameter, port or not. And an explicit ``{param: Port}`` entry is ignored when that
  parameter is already annotated with a port; the annotation wins.

  Forms::

    @Invert()                              # infer ports from the type hints
    @Invert(keys={'basket': 'golden'})     # pick keyed adapters
    @Invert({'basket': AppleBasketPort})   # explicit param -> port (no port annotation)
  """

  __slots__ = ('_explicit_ports', '_keys')

  def __call__(self, init: Init) -> Init:
    """Wrap ``init`` so its ``@Port``-typed parameters are filled in at construction time."""
    signature = inspect.signature(init)
    discovered, optional_names = DecoratorSupport.extract_port_parameters(get_type_hints(init))
    # A port annotation is the contract; the explicit map covers parameters without one.
    port_params: dict[str, type[Any]] = {**self._explicit_ports, **discovered}

    @functools.wraps(init)
    def wrapper(instance: Any, *args: Any, **kwargs: Any) -> None:
      supplied = signature.bind_partial(instance, *args, **kwargs).arguments
      for name, port in port_params.items():
        if name not in supplied:  # the caller always wins; that is the whole testing story
          kwargs[name] = self._inject(
            name=name,
            port=port,
            parameter=signature.parameters[name],
            optional=name in optional_names,
          )
        # Assigned before the body runs, so the body can already lean on self.<name>.
        setattr(instance, name, kwargs[name] if name in kwargs else supplied[name])
      init(instance, *args, **kwargs)

    return wrapper

  def __init__(
    self,
    ports: Mapping[str, type[Any]] | None = None,
    *,
    keys: Mapping[str, str] | None = None,
  ) -> None:
    """Capture explicit ``param -> port`` mappings and per-parameter adapter keys."""
    # Bare @Invert hands us the function as ``ports``; better a TypeError now than a riddle later.
    if callable(ports) and not isinstance(ports, Mapping):
      message = (
        f'@Invert must be applied with parentheses on {QualifiedName.of(ports)}: '
        'use @Invert() or @Invert(keys=...)'
      )
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
    """Resolve one parameter: its active adapter, or the default / ``None`` when allowed."""
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
