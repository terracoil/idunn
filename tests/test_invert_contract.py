"""The ``@Invert`` contract as declared: what is checked at decoration, and what has to wait.
Shape rules (names exist, mapped or keyed parameters are keyword-only, no stacking) read the code
object, so they fire at decoration on every version. Annotation rules (map versus annotation, keys
on ports only, port-annotated parameters keyword-only) need the type hints, so a forward reference
postpones them to the first call. The
generated modules exist because a forward reference is a module-level affair: a module that names a
class it defines further down, or never defines at all until the test hands it one.
"""

import functools
import importlib
import inspect
import re
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol

import pytest
from idunn import Adapter, AdapterNotFoundError, InvalidPortError, Invert, Port
from idunn.domain import FunctionShape, InvertDeclaration
from idunn.internal import ConstructorPlanner, LazyPlan
from idunn.testing import Harness

from _support import PackageWriter


@Port
class BasketPort(Protocol):
  def take(self) -> str: ...


@Adapter(BasketPort)
class GoldenBasket(BasketPort):
  def take(self) -> str:
    return 'golden'


class Sources:
  """Generated modules; each test gets its own name, since ``sys.modules`` outlives a test."""

  # Every hint names something defined *after* the function, or never: LaterPort and LaterValue
  # are handed in by the test, so it controls exactly when the forward reference starts to work.
  DANGLING = """
    from __future__ import annotations

    def pick(*, basket: LaterPort) -> str:
      return basket.take()

    def mapped(*, basket: LaterPort) -> str:
      return basket.take()

    def labelled(*, label: LaterValue) -> str:
      return label

    def positional(basket: LaterPort) -> str:
      return basket.take()
  """

  # The consumers come first and the port last, the order a forward reference exists for.
  FORWARD = """
    {future}
    from typing import Protocol
    from idunn import Adapter, Invert, Port

    class Feast:
      basket: LaterPort

      @Invert()
      def __init__(self, *, basket: LaterPort) -> None:
        pass

    class Node:
      parent: Node | None
      basket: LaterPort | None

      @Invert()
      def __init__(self, *, parent: Node | None = None, basket: LaterPort | None = None) -> None:
        self.parent = parent

    @Port
    class LaterPort(Protocol):
      def take(self) -> str: ...

    @Adapter(LaterPort)
    class LaterBasket(LaterPort):
      def take(self) -> str:
        return 'later'
  """

  # No future import and a name that never exists: legal on 3.14 (PEP 649) until someone looks.
  NEVER = """
    from idunn import Invert

    class Feast:
      @Invert(keys={'basket': 'golden'})
      def __init__(self, host: str, *, basket: NeverPort) -> None:
        pass
  """

  @staticmethod
  def load(writer: PackageWriter, name: str, source: str) -> ModuleType:
    """Write ``source`` as top-level module ``name`` and import it."""
    writer.module(name, source)
    return importlib.import_module(name)

  @staticmethod
  def shape(function: Callable[..., Any]) -> FunctionShape:
    """Return the shape of something that certainly has one."""
    found = FunctionShape.of(function)
    assert found is not None
    return found


@pytest.fixture
def writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PackageWriter:
  return PackageWriter(tmp_path=tmp_path, monkeypatch=monkeypatch)


# Shape rules: decoration, every version, no hints needed.


def test_an_unknown_name_in_the_map_or_keys_raises_at_decoration() -> None:
  with pytest.raises(TypeError, match=r"names 'baskt', which is not one of its parameters"):

    class Feast:
      @Invert(keys={'baskt': 'golden'})
      def __init__(self, *, basket: BasketPort) -> None:
        pass


@pytest.mark.parametrize('name', ['self', 'args', 'kwargs'])
def test_the_instance_slot_and_star_parameters_are_not_parameters_to_map(name: str) -> None:
  with pytest.raises(TypeError, match=f"names '{name}'"):

    class Feast:
      @Invert({name: BasketPort})
      def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass


def test_a_mapped_or_keyed_parameter_a_caller_could_fill_positionally_raises() -> None:
  owner = f'{__name__}.test_a_mapped_or_keyed_parameter_a_caller_could_fill_positionally_raises'

  with pytest.raises(
    TypeError, match=re.escape(f"{owner}.<locals>.Feast.__init__ maps or keys 'b")
  ):

    class Feast:
      @Invert({'basket': BasketPort})
      def __init__(self, basket: object) -> None:
        pass


def test_a_stacked_invert_raises_type_error_naming_the_function() -> None:
  owner = f'{__name__}.test_a_stacked_invert_raises_type_error_naming_the_function'

  with pytest.raises(
    TypeError, match=re.escape(f'more than once to {owner}.<locals>.Feast.__init__')
  ):

    class Feast:
      @Invert()
      @Invert()
      def __init__(self, *, basket: BasketPort) -> None:
        pass


def test_a_stacked_invert_is_caught_through_another_wrapping_decorator() -> None:
  def logged(function: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
      return function(*args, **kwargs)

    return wrapper

  with pytest.raises(TypeError, match='more than once'):

    class Feast:
      @Invert()
      @logged
      @Invert()
      def __init__(self, *, basket: BasketPort) -> None:
        pass


def test_invert_on_a_class_raises_type_error() -> None:
  class Feast:
    pass

  with pytest.raises(TypeError, match='can only decorate a function or an __init__'):
    Invert()(Feast)


def test_a_map_value_that_is_not_a_port_raises_before_seeing_the_function() -> None:
  with pytest.raises(InvalidPortError, match=r"'basket' -> builtins\.int"):
    Invert({'basket': int})


def test_a_map_value_that_is_not_even_a_class_raises_invalid_port_error() -> None:
  with pytest.raises(InvalidPortError, match="'basket' -> 5"):
    Invert({'basket': 5})  # type: ignore[dict-item]


def test_a_key_that_is_not_a_str_raises_type_error() -> None:
  with pytest.raises(TypeError, match="'basket': 7"):
    Invert(keys={'basket': 7})  # type: ignore[dict-item]


# Annotation rules: decoration when the hints resolve.


def test_a_map_entry_on_a_port_annotated_parameter_raises_instead_of_losing_quietly() -> None:
  # 1.x let the annotation win and ignored the map; two contracts for one parameter is a bug.
  with pytest.raises(InvalidPortError, match=r"maps 'basket' to .*already annotated with"):

    class Feast:
      @Invert({'basket': BasketPort})
      def __init__(self, *, basket: BasketPort) -> None:
        pass


def test_a_key_on_a_parameter_that_is_not_a_port_raises() -> None:
  with pytest.raises(InvalidPortError, match="keys 'label', which is not a port parameter"):

    class Feast:
      @Invert(keys={'label': 'golden'})
      def __init__(self, *, label: str) -> None:
        pass


def test_a_mapped_parameter_with_a_non_port_annotation_is_injected() -> None:
  class Feast:
    basket: object

    @Invert({'basket': BasketPort})
    def __init__(self, *, basket: object) -> None:
      pass

  with Harness.install(GoldenBasket):
    assert isinstance(Feast().basket, GoldenBasket)


def test_the_declaration_rides_on_the_wrapper() -> None:
  class Feast:
    @Invert(keys={'basket': 'golden'})
    def __init__(self, *, basket: BasketPort) -> None:
      pass

  declaration = InvertDeclaration.of(Feast.__init__)

  assert declaration is not None
  assert dict(declaration.keys) == {'basket': 'golden'}
  assert InvertDeclaration.of(GoldenBasket.__init__) is None


def test_the_declaration_is_a_frozen_copy_of_what_the_caller_passed() -> None:
  keys = {'basket': 'golden'}
  invert = Invert(keys=keys)

  class Feast:
    @invert
    def __init__(self, *, basket: BasketPort) -> None:
      pass

  keys['basket'] = 'changed'
  declaration = InvertDeclaration.of(Feast.__init__)

  assert declaration is not None
  assert declaration.keys['basket'] == 'golden'


# Forward references: the annotation rules wait, the shape rules do not.


def test_a_forward_referenced_port_and_a_self_reference_decorate_and_construct(
  writer: PackageWriter,
) -> None:
  module = Sources.load(
    writer, 'contract_forward', Sources.FORWARD.format(future='from __future__ import annotations')
  )
  with Harness.install(module.LaterBasket):
    child = module.Node(parent=module.Node())

    assert module.Feast().basket.take() == 'later'
    assert isinstance(child.parent, module.Node)
    assert child.basket.take() == 'later'


@pytest.mark.skipif(sys.version_info < (3, 14), reason='3.11-3.13 evaluate the hint at def')
def test_without_the_future_import_314_defers_too(writer: PackageWriter) -> None:
  module = Sources.load(writer, 'contract_forward_314', Sources.FORWARD.format(future=''))
  with Harness.install(module.LaterBasket):
    assert module.Feast().basket.take() == 'later'
    assert module.Node().parent is None


@pytest.mark.skipif(sys.version_info < (3, 14), reason='3.11-3.13 evaluate the hint at def')
def test_shape_checks_never_evaluate_a_hint_on_314(writer: PackageWriter) -> None:
  module = Sources.load(writer, 'contract_never_314', Sources.NEVER)
  init = module.Feast.__init__

  # The proof has teeth only if looking at the signature really does blow up here.
  with pytest.raises(NameError):
    inspect.signature(init)
  shape = ConstructorPlanner.check_shape(init, InvertDeclaration.frozen(ports={}, keys={}))

  assert shape.positional_limit == 1
  assert shape.keyword_only == ('basket',)
  with pytest.raises(NameError):
    module.Feast('host')  # the annotation rules ran at last, and the name never arrived


def test_shape_rules_still_fire_at_decoration_when_hints_are_deferred(
  writer: PackageWriter,
) -> None:
  module = Sources.load(writer, 'contract_dangling_shape', Sources.DANGLING)

  with pytest.raises(TypeError, match="names 'nope'"):
    Invert(keys={'nope': 'golden'})(module.pick)
  with pytest.raises(TypeError, match="maps or keys 'basket'"):
    Invert(keys={'basket': 'golden'})(module.positional)


def test_a_deferred_map_conflict_raises_at_the_first_call(writer: PackageWriter) -> None:
  module = Sources.load(writer, 'contract_dangling_map', Sources.DANGLING)
  mapped = Invert({'basket': BasketPort})(module.mapped)  # LaterPort does not exist yet: fine

  vars(module)['LaterPort'] = BasketPort

  with pytest.raises(InvalidPortError, match='already annotated with'):
    mapped()


def test_a_deferred_key_on_a_non_port_raises_at_the_first_call(writer: PackageWriter) -> None:
  module = Sources.load(writer, 'contract_dangling_key', Sources.DANGLING)
  labelled = Invert(keys={'label': 'golden'})(module.labelled)

  vars(module)['LaterValue'] = str

  with pytest.raises(InvalidPortError, match="keys 'label'"):
    labelled()


def test_a_deferred_plan_is_retried_until_the_name_exists(writer: PackageWriter) -> None:
  module = Sources.load(writer, 'contract_dangling_retry', Sources.DANGLING)
  pick = Invert()(module.pick)
  with Harness.install(GoldenBasket):
    with pytest.raises(NameError):
      pick()  # a failed plan is not cached
    vars(module)['LaterPort'] = BasketPort

    assert pick() == 'golden'


def test_lazy_plan_plans_eagerly_when_it_can_and_lazily_when_it_must(
  writer: PackageWriter,
) -> None:
  module = Sources.load(writer, 'contract_dangling_lazy', Sources.DANGLING)
  empty = InvertDeclaration.frozen(ports={}, keys={})
  lazy = LazyPlan(
    module.pick, shape=Sources.shape(module.pick), declaration=empty, keyword_only=False
  )

  assert lazy.try_now() is False
  assert lazy.ready is False
  vars(module)['LaterPort'] = BasketPort
  plan = lazy.get()

  assert lazy.ready is True
  assert [(p.name, p.port, p.key) for p in plan] == [('basket', BasketPort, None)]
  assert lazy.get() is plan

  def ready(*, basket: BasketPort) -> None:
    pass

  assert LazyPlan(
    ready, shape=Sources.shape(ready), declaration=empty, keyword_only=False
  ).try_now()


# Keyword-only ports: a positional argument can never land in a port.


@pytest.mark.parametrize('form', ['positional', 'positional-only'])
def test_a_port_declared_positionally_raises_at_decoration(form: str) -> None:
  def regular(self: object, basket: BasketPort) -> None:
    pass

  def slashed(self: object, basket: BasketPort, /) -> None:
    pass

  target = regular if form == 'positional' else slashed

  with pytest.raises(TypeError, match="port parameter 'basket' must be keyword-only"):
    Invert()(target)


def test_a_positional_port_in_a_function_raises_at_decoration_too() -> None:
  def take(basket: BasketPort) -> str:
    return basket.take()

  with pytest.raises(TypeError, match="port parameter 'basket' must be keyword-only"):
    Invert()(take)


def test_a_deferred_positional_port_raises_at_the_first_call(writer: PackageWriter) -> None:
  module = Sources.load(writer, 'contract_dangling_positional', Sources.DANGLING)
  positional = Invert()(module.positional)  # the hint does not resolve yet, so nothing to check

  vars(module)['LaterPort'] = BasketPort

  with pytest.raises(TypeError, match="port parameter 'basket' must be keyword-only"):
    positional()


def test_too_many_positionals_raise_before_anything_is_built() -> None:
  built: list[str] = []

  @Adapter(BasketPort, key='counted')
  class CountedBasket(BasketPort):
    def __init__(self) -> None:
      built.append('basket')

    def take(self) -> str:
      return 'counted'

  class Feast:
    @Invert(keys={'basket': 'counted'})
    def __init__(self, host: str, *, basket: BasketPort) -> None:
      self.host = host

  with Harness.install(CountedBasket):
    with pytest.raises(TypeError, match=r'Feast\.__init__ takes 1 positional argument but 2 were'):
      Feast('Bragi', CountedBasket())
    assert built == ['basket']  # only the one the caller made: nothing was injected
    assert Feast('Bragi').host == 'Bragi'  # a lone positional can only mean host
    assert built == ['basket', 'basket']


def test_a_star_args_consumer_takes_any_number_of_positionals() -> None:
  class Feast:
    basket: BasketPort

    @Invert()
    def __init__(self, *guests: str, basket: BasketPort) -> None:
      self.guests = guests

  with Harness.install(GoldenBasket):
    feast = Feast('Bragi', 'Iðunn')

  assert feast.guests == ('Bragi', 'Iðunn')
  assert feast.basket.take() == 'golden'


def test_undecorated_adapter_constructors_may_still_take_ports_positionally() -> None:
  @Port
  class ServicePort(Protocol):
    def run(self) -> str: ...

  @Adapter(ServicePort)
  class BasketService(ServicePort):
    def __init__(self, basket: BasketPort) -> None:  # the resolver passes it by keyword anyway
      self._basket = basket

    def run(self) -> str:
      return self._basket.take()

  class Feast:
    service: ServicePort

    @Invert()
    def __init__(self, *, service: ServicePort) -> None:
      pass

  with Harness.install(GoldenBasket, BasketService):
    assert ConstructorPlanner.KEYWORD_ONLY_PORTS is True
    assert Feast().service.run() == 'golden'


def test_function_shape_reads_names_kinds_defaults_and_the_positional_limit() -> None:
  class Feast:
    def __init__(
      self, host: str, /, guest: str = 'Bragi', *, basket: BasketPort, n: int = 2
    ) -> None:
      pass

  def serve(dish: str, *extras: str, basket: BasketPort) -> None:
    pass

  init = Sources.shape(Feast.__init__)
  function = Sources.shape(serve)

  assert (init.constructor, init.caller_positional, init.positional_only) == (
    True,
    ('host', 'guest'),
    ('self', 'host'),
  )
  assert init.named == ('host', 'guest', 'basket', 'n')
  assert dict(init.defaults) == {'guest': 'Bragi', 'n': 2}
  assert init.positional_limit == 2
  assert (function.constructor, function.named, function.positional_limit) == (
    False,
    ('dish', 'basket'),
    None,
  )
  assert FunctionShape.of(len) is None


def test_an_unregistered_port_still_raises_adapter_not_found() -> None:
  class Feast:
    @Invert()
    def __init__(self, *, basket: BasketPort) -> None:
      pass

  with pytest.raises(AdapterNotFoundError):
    Feast()


@pytest.mark.parametrize('kind', [staticmethod, classmethod])
def test_invert_above_a_method_descriptor_raises_at_decoration(kind: type[Any]) -> None:
  # Unwrapped, the descriptor looks like a function; wrapped, it would fail only when called
  # ("'classmethod' object is not callable", or an instance arriving as an extra positional).
  def peek(*args: object, basket: BasketPort) -> str:
    return basket.take()

  with pytest.raises(TypeError, match=f'must go beneath @{kind.__name__}'):
    Invert()(kind(peek))


def test_invert_beneath_a_method_descriptor_works_via_class_and_instance() -> None:
  class Kit:
    @staticmethod
    @Invert()
    def peek(*, basket: BasketPort) -> str:
      return basket.take()

    @classmethod
    @Invert()
    def named(cls, *, basket: BasketPort) -> str:
      return f'{cls.__name__}:{basket.take()}'

  with Harness.install(GoldenBasket):
    assert (Kit.peek(), Kit().peek()) == ('golden', 'golden')
    assert (Kit.named(), Kit().named()) == ('Kit:golden', 'Kit:golden')
