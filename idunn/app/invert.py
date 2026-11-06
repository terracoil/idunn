"""The ``@Invert`` decorator: where an object graph actually gets built."""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from idunn.domain import FunctionShape, InvalidPortError, InvertDeclaration, ParameterPlan
from idunn.internal import ConstructorPlanner, DecoratorSupport, LazyPlan, PortRegistry
from idunn.util import QualifiedName

from .idunn import Idunn

R = TypeVar('R')


class Invert:
  """Inject registered adapters into the ``@Port``-typed parameters of a constructor or function.
  Applied with parentheses (``@Invert()``). On an ``__init__``, every port parameter the caller
  left out is resolved from the :class:`Idunn` container when the constructor runs, and every port
  parameter, injected or supplied, is assigned to ``self.<name>`` before the body runs. On any
  other function (plain, method or static) the ports are passed in as keyword arguments at call
  time and nothing is assigned anywhere: the function simply receives them. Which form applies is
  decided by the name in the function's own ``def``, ``__init__`` or not, read from its code
  object, so where the function ends up stored does not matter.

  Either way a caller-supplied argument wins, which is what keeps consumers testable without the
  container, and there is no public ``resolve``: calling an ``@Invert()`` constructor or function
  is the only way to start a graph, so wiring code has nowhere to leak into business logic.

  A parameter typed ``Port | None``, or any port parameter with a default, is *optional*: with no
  active adapter it gets the default or ``None`` instead of an exception. ``keys`` picks a keyed
  adapter per parameter, right where the choice matters, and the explicit map types a parameter
  whose annotation is not a port. Both apply to adapter constructors too, when the resolver builds
  them as someone else's dependency.

  ``bootstrap='my_lib'`` is for libraries, which have no startup hook: a call that leaves at least
  one port parameter to injection runs the public ``Idunn().bootstrap('my_lib')`` first, after the
  positional check and the plan and before anything is injected, so the library wires itself on
  first use. Optional ports count, since discovery is what decides whether an adapter exists. The
  first call discovers, later ones are a cache hit, and a call that brings every port itself
  discovers nothing at all. A failure propagates unwrapped before ``self`` is touched, and the next
  call retries. The resolver passes an adapter constructor every planned port, so building one as
  a dependency never bootstraps. Options such as ``exclude`` are not on offer here: call
  ``Idunn().bootstrap(root, exclude=...)`` first yourself, and the first call wins.

  Checked at decoration, so a mistake fails at import next to its culprit: a map value that is not
  a port (``InvalidPortError``), a key that is not a ``str``, a ``bootstrap`` that is not a
  non-empty ``str``, a mapped or keyed name that is not a parameter, a mapped or keyed parameter
  that is not keyword-only, a second ``@Invert`` on the same function, and ``@Invert()`` above
  ``@staticmethod`` or ``@classmethod`` instead of beneath it (all ``TypeError``). A ``bootstrap``
  string that is not a dotted run of identifiers (``'.relative'``, ``'my lib'``, ``'a..b'``) raises
  ``ValueError``, judged from the spelling alone. A map entry on a port-annotated parameter, or a
  key on a non-port one, raises ``InvalidPortError`` too, while a port-annotated parameter a caller
  could fill positionally, and ``bootstrap=`` on a function with no port parameters, raise
  ``TypeError``; if a hint is a forward reference that cannot resolve yet, those four wait for the
  first call, when it can. The root itself is never imported or even looked up at decoration,
  which would be the import-time side effect ``bootstrap=`` exists to avoid. Port parameters are
  keyword-only, so a caller passing more positional arguments than the plain parameters take gets
  a ``TypeError`` before anything is built, and ``Feast('Bragi')`` can only ever mean the first
  plain parameter.

  Forms::

    @Invert()                                # infer ports from the type hints; ports go after '*'
    @Invert(keys={'basket': 'golden'})       # pick keyed adapters; keyed params go after '*'
    @Invert({'basket': AppleBasketPort})     # explicit param -> port; mapped params go after '*'
    @Invert(bootstrap='my_lib')              # wire my_lib on first use; mixes with the above
  """

  __slots__ = ('_declaration',)

  def __call__(self, function: Callable[..., R]) -> Callable[..., R]:
    """Wrap ``function`` so its port parameters are filled in when it is called."""
    if InvertDeclaration.of(function) is not None:
      message: str = (
        f'@Invert is applied more than once to {QualifiedName.of(function)}; one function gets '
        'one declaration. Merge the two into a single @Invert(...).'
      )
      raise TypeError(message)
    shape: FunctionShape = ConstructorPlanner.check_shape(function, self._declaration)
    lazy: LazyPlan = LazyPlan(function, shape=shape, declaration=self._declaration)
    lazy.try_now()  # annotation rules fire here, unless a forward reference makes them wait
    root: str | None = self._declaration.bootstrap
    wrapper: Callable[..., R] = (
      self._constructor(function, shape=shape, lazy=lazy, root=root)
      if shape.constructor
      else self._function(function, shape=shape, lazy=lazy, root=root)
    )
    self._declaration.attach(wrapper)
    return wrapper

  def __init__(
    self,
    ports: Mapping[str, type[Any]] | None = None,
    *,
    keys: Mapping[str, str] | None = None,
    bootstrap: str | None = None,
  ) -> None:
    """Capture the explicit map, the per-parameter keys and the bootstrap root, checked now."""
    # Bare @Invert hands us the function as ``ports``; better a TypeError now than a riddle later.
    if callable(ports) and not isinstance(ports, Mapping):
      message: str = (
        f'@Invert must be applied with parentheses on {QualifiedName.of(ports)}: '
        'use @Invert() or @Invert(keys=...)'
      )
      raise TypeError(message)
    explicit: dict[str, type[Any]] = dict(ports) if ports is not None else {}
    chosen: dict[str, str] = dict(keys) if keys is not None else {}
    unmarked: list[str] = [
      f'{name!r} -> {QualifiedName.of(port)}'
      for name, port in explicit.items()
      if not PortRegistry.is_port(port)
    ]
    if unmarked:
      message = f'@Invert maps parameters to classes not marked with @Port: {", ".join(unmarked)}'
      raise InvalidPortError(message)
    unnamed: list[str] = [
      f'{name!r}: {key!r}' for name, key in chosen.items() if not isinstance(key, str)
    ]
    if unnamed:
      message = f'@Invert keys must be str adapter keys: {", ".join(unnamed)}'
      raise TypeError(message)
    self._declaration: InvertDeclaration = InvertDeclaration.frozen(
      ports=explicit,
      keys={name: DecoratorSupport.plain_key(key) for name, key in chosen.items()},
      bootstrap=Invert._root(bootstrap),
    )

  @staticmethod
  def _constructor(
    init: Callable[..., R],
    *,
    shape: FunctionShape,
    lazy: LazyPlan,
    root: str | None,
  ) -> Callable[..., R]:
    limit: int | None = shape.positional_limit
    owner: str = QualifiedName.of(init)

    @functools.wraps(init)
    def wrapper(instance: Any, *args: Any, **kwargs: Any) -> R:
      # Redundant once ports are keyword-only, except that it fires before anything is built.
      if limit is not None and len(args) > limit:
        raise TypeError(Invert._too_many(owner=owner, limit=limit, given=len(args)))
      container: Idunn = Idunn()
      plan: tuple[ParameterPlan, ...] = lazy.get()
      if root is not None and Invert._missing(plan, kwargs):  # before self gets anything
        container.bootstrap(root)
      for parameter in plan:
        if parameter.name not in kwargs:  # ports arrive only by keyword, so kwargs is the truth
          kwargs[parameter.name] = container._inject(parameter)  # the caller always wins
        # Assigned before the body runs, so the body can already lean on self.<name>.
        setattr(instance, parameter.name, kwargs[parameter.name])
      return init(instance, *args, **kwargs)

    return wrapper

  @staticmethod
  def _function(
    function: Callable[..., R],
    *,
    shape: FunctionShape,
    lazy: LazyPlan,
    root: str | None,
  ) -> Callable[..., R]:
    limit: int | None = shape.positional_limit
    owner: str = QualifiedName.of(function)

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> R:
      if limit is not None and len(args) > limit:
        raise TypeError(Invert._too_many(owner=owner, limit=limit, given=len(args)))
      container: Idunn = Idunn()
      plan: tuple[ParameterPlan, ...] = lazy.get()
      if root is not None and Invert._missing(plan, kwargs):
        container.bootstrap(root)
      for parameter in plan:
        if parameter.name not in kwargs:
          kwargs[parameter.name] = container._inject(parameter)  # receives, assigns nothing
      return function(*args, **kwargs)

    return wrapper

  @staticmethod
  def _missing(plan: tuple[ParameterPlan, ...], kwargs: dict[str, Any]) -> bool:
    # Whether injection has anything to do, the only time discovery could matter. A loop, because
    # any() over a generator cost three times as much on 3.13, on a path that runs every call.
    missing: bool = False
    for parameter in plan:
      if parameter.name not in kwargs:
        missing = True
        break
    return missing

  @staticmethod
  def _root(bootstrap: str | None) -> str | None:
    # Shape only, by string: looking the root up would be the import-time side effect bootstrap=
    # exists to avoid. A shape error is a ValueError, since the type was right and the spelling not.
    if bootstrap is not None and (not isinstance(bootstrap, str) or not bootstrap):
      message: str = (
        '@Invert bootstrap= must be a non-empty str naming the package root to discover: '
        f'{QualifiedName.of(bootstrap)}'
      )
      raise TypeError(message)
    root: str | None = None if bootstrap is None else DecoratorSupport.plain_key(bootstrap)
    if root is not None and not all(part.isidentifier() for part in root.split('.')):
      message = (
        '@Invert bootstrap= must be a dotted package name whose every part is a Python '
        f'identifier, as you would import it: {QualifiedName.of(root)}'
      )
      raise ValueError(message)
    return root

  @staticmethod
  def _too_many(*, owner: str, limit: int, given: int) -> str:
    return (
      f'{owner} takes {limit} positional argument{"" if limit == 1 else "s"} but {given} '
      f'{"was" if given == 1 else "were"} given; its port parameters are keyword-only, so pass '
      'them by name'
    )
