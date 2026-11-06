"""The one rulebook for which parameters of an ``@Invert`` function or adapter get injected."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator, Mapping
from inspect import Parameter
from typing import Any, NoReturn, get_type_hints

from idunn.domain import (
  FunctionShape,
  InvalidPortError,
  InvertDeclaration,
  MissingTypeHintError,
  ParameterPlan,
)
from idunn.util import QualifiedName

from .decorator_support import DecoratorSupport


class ConstructorPlanner:
  """Turns a function plus its ``@Invert`` declaration into a tuple of :class:`ParameterPlan`.
  ``@Invert`` constructors, ``@Invert`` functions and adapter constructors all go through here, so
  "what counts as a port parameter" has exactly one answer. Shape rules read the code object only,
  so they hold at decoration on every Python version: every mapped or keyed name is a real
  parameter, and every mapped or keyed parameter is keyword-only (``TypeError``). Annotation rules
  need the type hints, so a forward reference that cannot resolve yet defers them to the first
  call: no parameter is both port-annotated and mapped, ``keys`` names only port parameters
  (``InvalidPortError``), and port-annotated parameters are keyword-only (``TypeError``; undecorated
  adapter constructors are exempt, since the resolver passes keywords anyway).
  """

  @staticmethod
  def check_shape(function: Callable[..., Any], declaration: InvertDeclaration) -> FunctionShape:
    """Apply the shape rules to an ``@Invert`` target and return its shape.
    Raises ``TypeError`` for anything without a code object (a class, a builtin), for a mapped or
    keyed name that is not a parameter (the instance slot, ``*args`` and ``**kwargs`` do not
    count), and for a mapped or keyed parameter a caller could fill positionally. Also for a
    ``staticmethod`` or ``classmethod`` object: unwrapped, it looks like a function, but the wrapper
    would be a plain function where a descriptor belongs, and fail only when called.
    """
    if isinstance(function, (staticmethod, classmethod)):
      message: str = (
        f'@Invert() must go beneath @{type(function).__name__}, not above it: '
        f'{QualifiedName.of(function)}'
      )
      raise TypeError(message)
    shape: FunctionShape | None = FunctionShape.of(function)
    if shape is None:
      message = f'@Invert can only decorate a function or an __init__: {QualifiedName.of(function)}'
      raise TypeError(message)
    unknown: list[str] = sorted(declaration.names.difference(shape.named))
    if unknown:
      message = (
        f'@Invert on {QualifiedName.of(function)} names {", ".join(map(repr, unknown))}, which '
        'is not one of its parameters'
      )
      raise TypeError(message)
    positional: list[str] = sorted(declaration.names.difference(shape.keyword_only))
    if positional:
      message = (
        f'@Invert on {QualifiedName.of(function)} maps or keys {", ".join(map(repr, positional))}, '
        "which must be keyword-only: declare it after '*'"
      )
      raise TypeError(message)
    return shape

  @classmethod
  def plan(
    cls,
    function: Callable[..., Any],
    *,
    shape: FunctionShape,
    declaration: InvertDeclaration,
  ) -> tuple[ParameterPlan, ...]:
    """Plan the port parameters of ``function`` in signature order, applying the annotation rules.
    Raises ``NameError`` while a hint is still a forward reference; callers that can wait (see
    :class:`LazyPlan`) wait. Port parameters must be keyword-only, always: both ``@Invert``
    wrappers read ports from ``kwargs`` alone, so a port passed positionally would be injected
    over and then collide with itself.
    """
    return cls._ports(
      function,
      shape=shape,
      declaration=declaration,
      keyword_only=True,
      hints=get_type_hints(function),
    )

  @classmethod
  def plan_adapter(cls, adapter: type[Any]) -> tuple[ParameterPlan, ...]:
    """Plan an adapter constructor for the resolver, honouring its own ``@Invert`` if it has one.
    An undecorated or plain ``@Invert()`` constructor resolves unkeyed. Every other named
    parameter needs a default, since Idunn injects ports and never values
    (``MissingTypeHintError``), and a port must not be positional-only, since the resolver passes
    keywords (``TypeError``). A constructor with no code object (``object.__init__``, a builtin
    base) has nothing to inject. The keyword-only rule binds decorated constructors only: the
    resolver passes every port by keyword, so an undecorated one has no wrapper to confuse. A hint
    that does not resolve raises ``MissingTypeHintError`` too, chained from the ``NameError``:
    unlike a consumer's plan, this one is wanted now, by a build that cannot wait for the name.
    """
    init: Callable[..., Any] = adapter.__init__
    found: FunctionShape | None = FunctionShape.of(init)
    declaration: InvertDeclaration | None = InvertDeclaration.of(init)
    plans: tuple[ParameterPlan, ...] = ()
    if found is not None:
      # Whatever the function is called, a class's __init__ gets the instance first.
      shape: FunctionShape = dataclasses.replace(found, constructor=True)
      hints: dict[str, Any] = cls._adapter_hints(adapter, init)
      plans = cls._ports(
        init,
        shape=shape,
        declaration=declaration if declaration is not None else InvertDeclaration(),
        keyword_only=declaration is not None,
        hints=hints,
      )
      cls._check_adapter_rest(adapter, shape=shape, hints=hints, plans=plans)
    return plans

  @staticmethod
  def _adapter_hints(adapter: type[Any], init: Callable[..., Any]) -> dict[str, Any]:
    # A port defined inside a function under `from __future__ import annotations` is a string no
    # module namespace can resolve, so the build gets an Idunn error naming the culprit, not a bare
    # NameError from typing's eval. Nothing is cached, so it succeeds once the name exists. The
    # message quotes the error rather than `exc.name`: a hint that calls something may raise a
    # NameError with no name at all, and "names None" would send its reader looking for a None.
    try:
      hints: dict[str, Any] = get_type_hints(init)
    except NameError as exc:
      message: str = (
        f'Cannot plan the constructor of {QualifiedName.of(adapter)}: evaluating its type hints '
        f'raised "{exc}". Define or import what a hint names at module level, where it can see it.'
      )
      raise MissingTypeHintError(message) from exc
    return hints

  @classmethod
  def _check_adapter_rest(
    cls,
    adapter: type[Any],
    *,
    shape: FunctionShape,
    hints: Mapping[str, Any],
    plans: tuple[ParameterPlan, ...],
  ) -> None:
    owner: str = QualifiedName.of(adapter)
    planned: set[str] = {plan.name for plan in plans}
    for name in shape.named:
      if name in planned and name in shape.positional_only:
        message: str = (
          f'{owner}.{name} is a positional-only port, but Idunn passes ports by keyword: '
          "move it after the '/'"
        )
        raise TypeError(message)
      if name not in planned and name not in shape.defaults:
        cls._refuse_value(owner=owner, name=name, hints=hints)

  @staticmethod
  def _parameter(
    function: Callable[..., Any],
    name: str,
    *,
    shape: FunctionShape,
    declaration: InvertDeclaration,
    keyword_only: bool,
    hints: Mapping[str, Any],
  ) -> ParameterPlan | None:
    annotated, optional = DecoratorSupport.port_from_annotation(hints.get(name, Parameter.empty))
    mapped: type[Any] | None = declaration.ports.get(name)
    key: str | None = declaration.keys.get(name)
    owner: str = QualifiedName.of(function)
    if mapped is not None and annotated is not None:
      message: str = (
        f'@Invert on {owner} maps {name!r} to {QualifiedName.of(mapped)}, but it is already '
        f'annotated with {QualifiedName.of(annotated)}: one parameter, one contract. Drop the map '
        'entry or the annotation.'
      )
      raise InvalidPortError(message)
    port: type[Any] | None = mapped if mapped is not None else annotated
    if key is not None and port is None:
      message = f'@Invert on {owner} keys {name!r}, which is not a port parameter'
      raise InvalidPortError(message)
    if keyword_only and annotated is not None and name not in shape.keyword_only:
      message = f"@Invert on {owner}: port parameter {name!r} must be keyword-only (after '*')"
      raise TypeError(message)
    return (
      None
      if port is None
      else ParameterPlan(
        name=name,
        port=port,
        key=key,
        optional=optional,
        default=shape.defaults.get(name, Parameter.empty),
      )
    )

  @staticmethod
  def _refuse_value(*, owner: str, name: str, hints: Mapping[str, Any]) -> NoReturn:
    # Not a port and no default: Idunn injects ports, never values, so there is nothing to pass.
    message: str = (
      f'Cannot constructor-inject {owner}.{name}: {QualifiedName.of(hints[name])} is not an '
      '@Port and no default value was supplied.'
      if name in hints
      else f'Missing constructor type hint for {owner}.{name}'
    )
    raise MissingTypeHintError(message)

  @classmethod
  def _ports(
    cls,
    function: Callable[..., Any],
    *,
    shape: FunctionShape,
    declaration: InvertDeclaration,
    keyword_only: bool,
    hints: Mapping[str, Any],
  ) -> tuple[ParameterPlan, ...]:
    planned: Iterator[ParameterPlan | None] = (
      cls._parameter(
        function,
        name,
        shape=shape,
        declaration=declaration,
        keyword_only=keyword_only,
        hints=hints,
      )
      for name in shape.named
    )
    return tuple(plan for plan in planned if plan is not None)
