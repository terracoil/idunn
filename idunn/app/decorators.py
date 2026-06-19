"""The @Port, @Adapter, and @Invert decorators."""

import functools
import inspect
from collections.abc import Callable, Iterable, Mapping
from typing import Any, TypeVar, get_type_hints, overload, runtime_checkable

from idunn.domain import AdapterDeclaration, InvalidAdapterError, InvalidPortError, LifecycleEnum
from idunn.internal import DecoratorSupport

from .idunn import Idunn

T = TypeVar('T', bound=type[Any])
Init = Callable[..., None]


def Port(cls: T) -> T:
  """Mark a Protocol as an Idunn port."""
  if not getattr(cls, '_is_protocol', False):
    message = f'@Port can only be applied to Protocol classes: {cls.__qualname__}'
    raise InvalidPortError(message)

  cls.__idunn_port__ = True
  return runtime_checkable(cls)


def Adapter(
  port: type[Any],
  *,
  key: str | None = None,
  lifecycle: LifecycleEnum | str = LifecycleEnum.TRANSIENT,
  envs: Iterable[str] | str | None = None,
) -> Callable[[T], T]:
  """Declare a concrete class as an adapter for a port.

  Without ``key`` the adapter is *unkeyed*: it answers plain ``@Invert`` injection
  — exactly one unkeyed adapter may be active per port in any environment.

  With ``key`` the adapter is *opt-in*: it answers only ``@Invert(keys={...})`` and
  is ignored by unkeyed resolution, so it never competes with the plain
  implementation.
  """
  if not getattr(port, '__idunn_port__', False):
    message = f'Adapter port is not marked with @Port: {port.__qualname__}'
    raise InvalidPortError(message)

  lifecycle_value = LifecycleEnum(lifecycle)
  env_values = DecoratorSupport.normalize_envs(envs)

  def decorate(cls: T) -> T:
    if not isinstance(cls, type):
      message = f'@Adapter can only be applied to classes: {cls!r}'
      raise InvalidAdapterError(message)
    declaration = AdapterDeclaration(
      port=port,
      key=key,
      lifecycle=lifecycle_value,
      envs=env_values,
    )
    cls.__idunn_adapter__ = True
    cls.__idunn_adapter_declaration__ = declaration
    return cls

  return decorate


@overload
def Invert(init: Init) -> Init: ...


@overload
def Invert(
  init: Mapping[str, type[Any]] | None = ...,
  *,
  keys: Mapping[str, str] | None = ...,
) -> Callable[[Init], Init]: ...


def Invert(
  init: Init | Mapping[str, type[Any]] | None = None,
  *,
  keys: Mapping[str, str] | None = None,
) -> Init | Callable[[Init], Init]:
  """Auto-inject registered adapters for ``@Port``-typed constructor parameters.

  Decorate a constructor; every parameter whose type hint is a ``@Port`` is
  resolved from the process-wide :class:`Idunn` container at construction time
  and assigned to ``self.<name>`` (the body may override; a caller-supplied
  argument always wins). Constructing the decorated object is the sanctioned way
  to start an object graph — there is no public ``resolve``.

  A parameter typed ``Port | None`` (or any ``@Port`` parameter with a default) is
  *optional*: if no adapter is active it falls back to the default / ``None``
  instead of raising. Pick a *keyed* adapter with ``@Invert(keys={'param': 'name'})``,
  choosing right at the point of use.

  Forms::

    @Invert                                # infer ports from the type hints
    @Invert(keys={'basket': 'golden'})     # pick keyed adapters
    @Invert({'basket': AppleBasketPort})   # explicit param -> port (no annotation)
  """
  explicit_ports: dict[str, type[Any]] = {}
  if isinstance(init, Mapping):
    explicit_ports = dict(init)
    init = None
  key_map: dict[str, str] = dict(keys) if keys is not None else {}

  def decorate(func: Init) -> Init:
    signature = inspect.signature(func)
    hints = get_type_hints(func)
    discovered, optional_params = DecoratorSupport.extract_port_parameters(hints)
    port_params: dict[str, type[Any]] = {**explicit_ports, **discovered}

    @functools.wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> None:
      supplied = signature.bind_partial(self, *args, **kwargs).arguments
      container = Idunn()
      for name, port in port_params.items():
        key = key_map.get(name)
        parameter = signature.parameters[name]
        optional = name in optional_params or parameter.default is not inspect.Parameter.empty
        if name in supplied:
          value = supplied[name]  # a caller-supplied argument always wins
        elif optional and not container._has(port, key):
          # optional dep with no active adapter: fall back to the default (or None)
          value = None if parameter.default is inspect.Parameter.empty else parameter.default
          kwargs[name] = value
        else:
          value = container._inject(port, key)  # required, or an adapter is available
          kwargs[name] = value
        setattr(self, name, value)  # the port always lands on self.<name>
      func(self, *args, **kwargs)

    return wrapper

  return decorate if init is None else decorate(init)
