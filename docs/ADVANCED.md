# Idunn Advanced Notes

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-landscape-2560x900.png)

The [README](../README.md) covers normal usage: three decorators, one discovery call, one adapter
per port. This document holds everything else: choosing between adapters, the full `@Invert`
contract, discovery options, inspection, testing, the exceptions, and the lines Idunn will not
cross.

> Everything here is supported, but little of it belongs in business logic. If these features start
> showing up in everyday code, step back: the decorators are almost always enough.

## Contents

- [Design stance](#design-stance)
- [When resolution happens](#when-resolution-happens)
- [The `@Invert` contract in full](#the-invert-contract-in-full)
- [Choosing between adapters](#choosing-between-adapters)
- [Discovery options](#discovery-options)
- [Inspecting the graph](#inspecting-the-graph)
- [Testing](#testing)
- [Exceptions](#exceptions)
- [Limitations and non-features](#limitations-and-non-features)
- [Maintainer notes](#maintainer-notes)

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Design stance

| Question | Answer |
|---|---|
| Define a dependency? | A `Protocol` marked `@Port`. |
| Bind an implementation? | A class marked `@Adapter(port, ...)`. |
| Receive dependencies? | Decorate the consumer's `__init__`, or a function, with `@Invert()`. |
| Register everything? | `Idunn().autodiscover('my_app')` once at startup, or, in a library, `@Invert(bootstrap='my_lib')` on its consumers (or `Idunn().bootstrap('my_lib')` from its entry points). |
| Does `@Adapter` make the class implement the port? | No. The class must satisfy the Protocol itself. |
| When is injection done? | When an `@Invert()` constructor or function runs. Never at decoration or discovery. |
| Several adapters for one port? | `envs=` separates them by environment; `key=` makes one opt-in. |
| Port parameters? | Keyword-only, after `*`. |
| Optional dependency? | Type the parameter `SomePort \| None`, or give it a default. |
| Field, setter, or value injection? | No. Ports only, as constructor or function parameters. |
| Config files, scanning outside the root, name-based guessing? | No, no, and no. |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## When resolution happens

Decorators construct nothing. `@Port` and `@Adapter` attach metadata; `@Invert()` wraps a
constructor or function. Discovery imports the modules under the root so the decorators run, then
registers the decorated classes; it constructs nothing either. Apples are catalogued at discovery
and picked at construction, never the other way round.

Construction fires when an `@Invert()`-decorated object is built, or an `@Invert()` function is
called:

```python
feast = Feast('Bragi')  # @Invert resolves Feast's @Port parameters, then runs __init__
served = harvest('Asgard')  # the same, for a function: its ports arrive as keyword arguments
```

At that moment Idunn:

1. with `@Invert(bootstrap='my_lib')`, and at least one port parameter the caller did not supply,
   runs `Idunn().bootstrap('my_lib')`: a discovery on the first call, a cache hit afterwards. It
   comes after the positional check and the plan, so a mistake there raises before any discovery,
   and before anything is injected, so a discovery failure leaves `self` untouched;
2. selects the active adapter for each `@Port`-typed parameter the caller did not supply (inside a
   `Harness.override` block, the stand-in instead; see [Testing](#testing));
3. plans that adapter's constructor once (cached until `reset()`), honouring its own `@Invert` keys
   and map, and recursively resolves its `@Port` parameters, passing every one by keyword, so an
   adapter constructor's own `bootstrap=` never fires during a build;
4. instantiates dependencies first, then the adapter, and checks the instance satisfies the port;
5. builds each `SINGLETON` once and caches it, and rebuilds `TRANSIENT` ones each time
   (`lifecycle=` also accepts the lowercase strings `'singleton'` and `'transient'`);
6. on a constructor, assigns every port parameter to `self.<name>`, then runs the body; a function
   just receives them as keyword arguments.

Dependency order is worked out at resolution time, not registration time, so registration order
never matters. Two adapters that depend on each other raise `InjectionCycleError`, which is kinder
than the alternative. When a `SINGLETON` is about to be built for the first time, Idunn walks the
graph it is about to make before building any of it, so a loop through a singleton's parameters
raises before a single constructor in that graph has run.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## The `@Invert` contract in full

```python
@Invert()  # infer ports from the type hints
@Invert(keys={'basket': 'wild'})  # pick keyed adapters per parameter (declared after '*')
@Invert({'basket': AppleBasketPort})  # explicit param -> port, for a hint that is not a port
@Invert(bootstrap='my_lib')  # discover my_lib first when a port is missing; mixes with the rest
```

- **On a constructor it assigns `self.<name>`** for every port parameter, injected or
  caller-supplied, before the wrapped body runs, and forwards the same value into the body as a
  normal argument.
- **Functions.** On anything not named `__init__` (a plain function, a method, a static method),
  `@Invert()` fills the port parameters at call time and passes them as keyword arguments, and
  assigns nothing anywhere: no `self.<name>`, no attribute on the function. Every other rule on
  this list applies unchanged. The form comes from the name in the function's own `def`, read
  from its code object, not from the attribute it ends up stored under: a method called
  `handle(self, ...)` receives its ports like any function, and so does a function defined under
  another name and then assigned as `__init__` (no `self.<name>` for it).

  ```python
  @Invert(keys={'notifier': 'sms'})
  def remind(user: str, *, notifier: NotifierPort, logger: LoggerPort | None = None) -> None:
    notifier.send(user)
    if logger is not None:
      logger.write(f'reminded {user}')


  remind('Bragi')  # sms notifier injected; logger is None unless a LoggerPort adapter is active
  ```

- **A caller-supplied argument always wins.** Passing the parameter skips injection for it, which
  keeps the class, or the function, trivially testable.
- **Port parameters are keyword-only.** Declare every port after `*`, annotated, mapped or keyed:
  with `__init__(self, host: str, *, basket: AppleBasketPort)`, `Feast('Bragi')` can only mean
  `host`, and a positional argument can never land in a port. A port declared positionally
  (`/` included) raises `TypeError` at decoration, or at the first call if its hint is a forward
  reference that cannot resolve yet. A call passing more positional arguments than the plain
  parameters take raises `TypeError` before anything is built. Undecorated adapter constructors are
  exempt, since the resolver passes every port by keyword; the samples here use `*` anyway.
- **Resolution is recursive.** If the chosen adapter's own constructor takes `@Port` parameters,
  those resolve first, all the way down.
- **Optional dependencies.** A parameter typed `SomePort | None`, or any `@Port` parameter with a
  default, is optional: when no adapter is active it receives the default, or `None`, instead of
  raising `AdapterNotFoundError`. The same rule applies inside an adapter's own constructor.
- **Keyed selection at the point of use.** `keys={'param': 'name'}` picks a keyed adapter where it
  is consumed rather than in a container call elsewhere. Keys apply wherever `@Invert(keys=...)`
  decorates something: a consumer's constructor, an adapter's constructor or a function. A plain
  `@Invert()` or undecorated adapter constructor resolves unkeyed, so a keyed adapter never sneaks
  into a constructor that did not ask for it by name.
- **Explicit mapping.** `@Invert({'param': SomePort})` injects a parameter whose annotation is
  missing or is not a port. If the parameter is annotated with a `@Port` as well, `@Invert` raises
  `InvalidPortError`: one parameter, one contract. An adapter constructor's map is honoured too.
- **Bootstrapping on first use.** `bootstrap='my_lib'` (keyword-only, a dotted package name spelled
  as you would `import` it) is for libraries. A call that leaves at least one port parameter to
  injection, an optional one included (discovery is what decides whether an adapter exists), first
  runs the public `Idunn().bootstrap('my_lib')` with its default options, once per call at most. So
  it inherits the gate whole: cached per root until `reset()`, one discovery shared by concurrent
  first calls, safe at import time and on re-entry, and a failure (a `DiscoveryError`, a root that
  does not import) propagates unwrapped and is retried by the next call. A call that supplies every
  port discovers nothing. Nothing is imported at decoration, and the root is not even looked up. The
  resolver passes an adapter constructor every planned port, fallbacks included, so an adapter
  wearing `bootstrap=` never discovers while it is being built as a dependency. `exclude` and
  `strict` are not on offer: a library that needs them calls
  `Idunn().bootstrap('my_lib', exclude=...)` itself first, and the first call for a root wins.
  `bootstrap=` on a function with no port parameters could never fire, so it raises `TypeError`.
- **Checked at decoration.** A mistake fails at import, next to its culprit. A map value that is
  not a port, a map entry on a port-annotated parameter, and a key on a parameter that is not a
  port raise `InvalidPortError`. A key that is not a `str`, a mapped or keyed name that is not a
  parameter (the instance slot, `*args` and `**kwargs` do not count), a port parameter (annotated,
  mapped or keyed) that is not keyword-only, a `bootstrap` that is not a non-empty `str` or that
  sits on a function with no port parameters, a second `@Invert` on the same function, `@Invert()`
  on anything but a function, and `@Invert()` above `@staticmethod` or `@classmethod` raise
  `TypeError`. It belongs beneath them, on the plain function, where it has a function to wrap;
  above them it would hand the class a plain function where a descriptor belongs. A `bootstrap`
  string that is not a dotted run of identifiers (`'.relative'`, `'my lib'`, `'a..b'`) raises
  `ValueError`, judged from the spelling alone, since looking it up is exactly what decoration
  must not do.
- **Forward references.** A hint may name a class defined further down the module, or the class
  being defined (`parent: Node | None` inside `Node`), wherever Python allows it:
  `from __future__ import annotations`, or 3.14 without it. The shape checks read the function's
  code object and never evaluate a hint, so they still fire at decoration. The four checks that
  need the hints (map versus annotation, keys on ports only, port-annotated parameters
  keyword-only, `bootstrap=` with a port to fire for) wait for the first call if a hint cannot
  resolve yet, and raise there instead, before any discovery. An adapter constructor cannot wait,
  since the resolver plans it on the way to building it, so a hint that does not resolve then (a
  port defined inside a function under `from __future__ import annotations`, say) raises
  `MissingTypeHintError` naming the adapter and the name, and the next build tries again.
- **Parentheses are required.** `Invert` is a class; applying it bare raises `TypeError` at
  decoration rather than something stranger later.

```python
class Service:
  @Invert()
  def __init__(self, *, logger: LoggerPort | None = None) -> None:
    self.logger = logger  # None if nothing satisfies LoggerPort
```

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Choosing between adapters

Most ports have one implementation and need none of this. When a port has several, two decorator
arguments tell them apart, and one rule governs both: **an unkeyed resolve only ever sees unkeyed
adapters.** Keyed adapters are opt-in; you address them by name or they stay in the cellar.

### By environment

When the same role needs different implementations in dev, test and production, put the environment
in the decorator. The adapters are never active at once, so an unkeyed resolve still has one answer
and the consumer never changes.

```python
@Adapter(PaymentPort, envs={'prod'})
class StripePaymentAdapter(PaymentPort): ...


@Adapter(PaymentPort, envs={'test', 'ci'})
class FakePaymentAdapter(PaymentPort): ...
```

| `envs=` | Active when |
|---|---|
| `None` (default) | Every environment. |
| `'test'` or `{'test'}` | The active environment is `test`. |
| `{'test', 'ci'}` | The active environment is `test` or `ci`. |
| `set()` or `[]` | Never. Legal, though it is hard to think of a reason. |

The active environment comes from `Idunn().reset(environment=...)`, then the `IDUNN_ENV` variable,
then the default `local`. It is fixed when `Idunn()` is first created and again on each `reset()`,
never per resolve, so changing `IDUNN_ENV` mid-run does nothing until the next reset. `Idunn()`
itself takes no arguments, so `reset()` is the one place to choose; `Idunn(environment='ci')`
raises `TypeError` rather than being honored once and ignored forever after. Names are
stripped and lowercased with `_` turned into `-`, so `My_Env` and `my-env` are the same place. A
blank name means `local`, and the result must match `[a-z0-9][a-z0-9.-]*` without containing `..`.
`Idunn().environment` reports the name in force, normalized.

### By key

When several implementations are valid in the same environment, give each a key and choose at the
point of use:

```python
@Adapter(NotifierPort, key='email')
class EmailNotifier(NotifierPort): ...


@Adapter(NotifierPort, key='sms')
class SmsNotifier(NotifierPort): ...


class Reminder:
  notifier: NotifierPort  # assigned by @Invert

  @Invert(keys={'notifier': 'sms'})
  def __init__(self, *, notifier: NotifierPort) -> None:
    pass
```

If `email` and `sms` are the only adapters for `NotifierPort`, a plain `@Invert()` parameter typed
`NotifierPort` raises `AdapterNotFoundError`: there is no unkeyed apple in the basket. Pick one with
`keys=`, or register an unkeyed adapter as the default.

A key is a `str`, and a `StrEnum` member is one. Idunn keeps it as its plain value, so `'sms'` and
`Channel.SMS` find the same adapter, and `describe()` and error messages say `'sms'` rather than
`<Channel.SMS: 'sms'>`.

### Collisions

A key only has to be unique within an environment, so one key can name different adapters in
environments that never overlap:

```python
@Adapter(PaymentPort, key='primary', envs={'prod'})
class StripePaymentAdapter(PaymentPort): ...


@Adapter(PaymentPort, key='primary', envs={'test'})
class FakePaymentAdapter(PaymentPort): ...
```

Two adapters that share a port and key (unkeyed counts as the same "no key") and are both active in
an overlapping environment raise `InvalidAdapterError` at registration, and the discovery run that
hits the collision registers nothing at all. An env-agnostic adapter overlaps with everything.
Idunn refuses to guess which apple you meant, and refuses at startup rather than at the first
unlucky request.

Two `@Adapter` lines on one class collide sooner still: the second raises `InvalidAdapterError` at
import, because only one declaration could ever win, so one of the two lines was always wrong. A
subclass may wear its own `@Adapter`; it is a different class and registers as one, while an
undecorated subclass stays invisible to discovery, and `Harness.install` refuses it for the same
reason: it inherits the attribute, not the badge.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Discovery options

`autodiscover` and `bootstrap` share one signature:

```python
Idunn().autodiscover(
  'my_app',
  exclude=(),  # extra dotted-path parts to skip, as fnmatch patterns; added to the defaults
  strict=True,  # raise DiscoveryError on an unimportable module instead of skipping it
)
```

- **What is imported.** Every module under the root, the root itself included, directories without
  an `__init__.py` too. Three things are never imported: any dotted part named `__main__`, any part
  that is not a valid Python identifier (`my-scripts/`, `0001_initial.py`), and test modules
  (`tests`, `test`, `test_*`, `*_test`, `conftest`). Only classes bound at module level count, and a
  class registers through the one module that defines it, so a re-export is counted once and a
  class imported from outside the root is not registered through it.
- **The running `__main__`.** `python -m my_app.main` runs `main.py` as `__main__`. When discovery
  reaches that module it reuses the running copy instead of importing a second one, so a port or
  adapter declared in the entry module still works. A script run by path (`python my_app/main.py`)
  cannot be matched, so run entry points with `-m`.
- **`exclude`.** Patterns are `fnmatchcase` globs matched against each dotted part *below* the root;
  a matching package part prunes its whole subtree. They add to the test defaults, and a bare string
  counts as one pattern (`exclude='migrations'`). Because matching is per part, a pattern containing
  a dot (`'legacy.old'`) matches nothing, silently; use `'old'`, which skips every part named `old`
  under the root, or `'legacy'` for the whole subtree. The root's own name never matches, so to
  discover in-package test fakes on purpose, make the test package the root:
  `autodiscover('my_app.tests')`.
- **`strict`.** All modules import before anything registers, so with `strict=True` an unimportable
  module raises `DiscoveryError` naming it and leaves the catalog untouched; `bootstrap` does not
  cache the failure. With `strict=False` the module is skipped and listed in `skipped_modules`. Only
  `Exception` is caught: a module that calls `sys.exit()` or parses `argv` at import raises
  `SystemExit`, which is not swallowed. Prefer `exclude` for such modules. Registration is
  all-or-nothing too: each run validates everything it found as one batch, so a collision raises
  `InvalidAdapterError` and leaves the catalog exactly as it was.
- **Keep modules import-safe.** Everything under the root is imported at discovery, so module bodies
  should only define things. Work belongs behind `if __name__ == '__main__':` or in functions.
- **Root must be importable.** Pass the package's dotted name exactly as you would `import` it; a
  file path does not work. The root sits outside the `strict` handling: a missing root raises
  `ModuleNotFoundError`, and a root whose `__init__` fails raises its own error, whatever `strict`
  says.
- **Root must live in directories.** Discovery finds modules by walking the package's directories,
  so a package that Python imports from a zip (a zipapp, an egg, some frozen bundles) cannot be
  scanned. It raises `DiscoveryError` before anything registers, whatever `strict` says: there is
  no module to list in `skipped_modules`, and a root nobody can read is a setup problem, not an
  unlucky import. Install such packages unpacked.
- **`ReportMap`.** Both calls return a `TypedDict` of strings: `root_package`, `imported_modules`
  (sorted, root included), `skipped_modules`, `registered_ports`, and `registered_adapters`. The
  last two list only the classes *this call* registered, so a repeat run reports none; the report
  `bootstrap` caches covers every run of the root's first bootstrap (below). Class names are fully
  qualified. Import it as `from idunn import ReportMap` when you annotate a stored report.
- **Multiple roots accumulate.** Registration is idempotent and the catalog is shared, so call
  discovery once per package that contributes adapters. Each root registers only the classes defined
  under it.
- **`bootstrap` caches per root.** The first call for a root discovers with the options given. Later
  calls for that root return the same report without rescanning and ignore their options. Distinct
  roots are tracked independently, failures are not cached, and `reset()` forgets the cache along
  with the registrations. No lock is held while modules import. Concurrent first calls wait for one
  discovery and share its report. A call made while a module is being imported runs its own
  discovery instead of waiting, so it cannot deadlock against another thread's discovery. If two
  threads' discoveries each need a module the other is halfway through importing, Python breaks
  the tie itself: one of those imports fails, discovery treats it like any other import error, and
  a retry is safe. Whatever the failed attempt's other runs registered stays registered, and the
  retry's cached report lists it too. `@Invert(bootstrap=...)` is just another caller, with the
  default options: to discover with `exclude=`, call `bootstrap` yourself before the first
  consumer does.
- **Re-entrant and import-time `bootstrap`.** A module may call `bootstrap` while it is being
  imported, in this thread or another, and that includes a module under the root calling it for
  its own root, or building an `@Invert(bootstrap=...)` consumer that does. Every such run is
  merged into the one cached report, so nothing it registers goes missing, wherever in the module
  the call sits. The call itself returns its own run's report, which lists only what that run could
  see: a module that calls at its top has defined nothing yet. The first call normally returns the
  cached report itself. Only when an import-time run outlives it (one started by a module outside
  the root, say) does it get the merge so far, and the cache gets the rest when that run finishes.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Inspecting the graph

`Idunn().describe()` renders the port-to-adapter bindings for the current environment. It is built
from the same structured snapshot the resolver selects from, so what it prints is what an unkeyed
resolve would pick, not what someone hoped it would.

```python
Idunn().autodiscover('my_app')
print(Idunn().describe())
```

```text
Environment: test

my_app.ports.PaymentPort
  selected: my_app.adapters.fake.FakePaymentAdapter
  - my_app.adapters.fake.FakePaymentAdapter key=None envs=ci,test
  - my_app.adapters.stripe.StripePaymentAdapter key=None envs=prod singleton
```

Adapters are listed in registration order, which for discovery is sorted module order: `fake` before
`stripe`, whatever the environment. `envs=*` marks an adapter active everywhere. A port with no
active unkeyed adapter shows `selected: <none>`: its adapters may all be keyed, all belong to other
environments, or not exist yet.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Testing

`Idunn` is one process-wide container, which is convenient right up until two tests share it.
Three tools keep them apart, from the blunt to the precise.

**Reset around every test.** `reset()` keeps the same object, empties registrations, cached
singletons, overrides and the `bootstrap` cache, and rebinds the environment. An autouse fixture
does it for every test, before and after, so a test that forgets to clean up cannot spoil the next:

```python
import pytest
from idunn import Idunn


@pytest.fixture(autouse=True)
def _reset_idunn():
  Idunn().reset(environment='local')
  yield
  Idunn().reset(environment='local')
```

`reset(environment=...)` resolves the environment from its argument, then `IDUNN_ENV`, then `local`.
Because a reset empties the catalog, run it before discovery, not after; the other order is a very
thorough way to test nothing.

**Fakes with an environment of their own.** When the fakes are real classes worth keeping, give
them a package outside the application root and an environment nobody deploys, and let discovery
do the wiring:

```python
# my_app_fakes/baskets.py
from idunn import Adapter
from my_app.ports import AppleBasketPort


@Adapter(AppleBasketPort, envs={'test'})
class WaxBasket:
  def take_apple(self) -> str:
    return 'a wax apple, very convincing'
```

```python
@pytest.fixture
def fake_orchard() -> None:
  Idunn().reset(environment='test')
  Idunn().autodiscover('my_app')
  Idunn().autodiscover('my_app_fakes')
```

The production adapters it replaces must stay out of `test`: give them `envs={'local', 'prod'}`
(or whatever your deployments are called). An adapter with no `envs` is active everywhere, `test`
included, so it would collide with the fake, loudly, at the second `autodiscover`.

**`idunn.testing.Harness`, for one test.** For a stand-in that lives one test long, borrow the
harness. It is not the public register the facade refuses to have: everything it does is undone
when its block ends.

```python
from idunn.testing import Harness


def test_feast_with_a_wax_basket() -> None:
  with Harness.override(AppleBasketPort, WaxBasket()):
    assert Feast('Bragi').basket.take_apple() == 'a wax apple, very convincing'


@Harness.install(GoldenAppleBasketAdapter)
def test_feast_with_the_real_thing() -> None:
  assert Feast('Bragi').basket.take_apple() == 'youth restored'
```

- `install(*adapters)` registers `@Adapter` classes for the block as one all-or-nothing batch, the
  same one discovery uses, so a collision raises `InvalidAdapterError` before the block runs, with
  nothing registered. It is also how adapters defined inside a test function, where discovery
  cannot reach them, get in at all.
- `override(port, instance, *, key=None)` makes `port` (with `key`) resolve to `instance`, ahead
  of adapter selection: in every environment, with no adapter registered, wherever the port is
  injected (a consumer, another adapter's constructor, an optional parameter). A caller-supplied
  argument still wins. A port not marked `@Port` raises `InvalidPortError`, and an instance that
  does not satisfy the port raises `InvalidAdapterError`, both before the block runs.
- A library's `bootstrap=` consumer discovers into whatever block is open, so `install` a rival
  adapter for one of the library's ports and the library's own adapter lands in the same slot:
  `InvalidAdapterError` at the consumer's first use, an `override` on top notwithstanding (the port
  is still left to injection), or at the `install` itself once the root is discovered. To stand in
  for a library's port, `override` it, or pass it by name.
- On exit, error or not, a block puts back exactly what it found: registrations, singletons,
  overrides, `bootstrap` reports and the environment. A singleton built against a fake leaves
  with the fake, and a `bootstrap` inside an install leaves no report vouching for registrations
  that are gone. Blocks nest and unwind last in, first out. Driven by hand out of that order, an
  outer block's `__exit__` raises `RuntimeError` and restores nothing, and the inner block's exit
  then puts back what the outer one found, so neither block's wiring outlives the pair.
- An override reaches what is built inside its block. A singleton built before the block keeps the
  dependency it was built with, so open the block before anything builds it. A `reset()` inside the
  block is no shortcut: it drops the override along with the singleton.
- As decorators, both re-enter on every call. They wrap plain functions only: an `async def` test
  hands back its coroutine before a line of it runs, so put the `with` inside it instead.
- The harness is process-wide, like the container: one test at a time per process. `pytest-xdist`
  workers are separate processes, so they are fine; tests on threads side by side are not.

One staleness to know about: an adapter's constructor plan is worked out on its first build and
kept until the next `reset()` (a harness block keeps it too, since it depends only on the class).
A test that monkeypatches an adapter's `__init__` after that keeps the old plan until it resets.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Exceptions

All inherit from `IdunnError` and import from `idunn`, so one `except IdunnError` covers every
class below:

| Class | Raised when |
|---|---|
| `InvalidPortError` | `@Port` is applied to anything but a Protocol (`Port(5)` included), an adapter names an unmarked port, an `@Invert` map value is not a port, a parameter is both port-annotated and mapped, `keys` names a parameter that is not a port, or `Harness.override` is handed something that is not a port. |
| `InvalidAdapterError` | `@Adapter` is applied to a non-class or twice to one class, `Harness.install` is handed a class that never wore `@Adapter` (an undecorated subclass of an adapter included), two adapters collide (the discovery run or `Harness.install` that hits it registers nothing), or a built instance or a `Harness.override` stand-in does not satisfy its port. |
| `AdapterNotFoundError` | No active adapter exists for a requested port and the parameter is not optional. |
| `DiscoveryError` | A module below the discovery root fails to import and `strict=True`, or the root package does not live in a directory (a zip, say), whatever `strict` says. |
| `MissingTypeHintError` | An adapter constructor parameter without a default has no annotation, or one that is not a port, or a constructor hint does not resolve (chained from the `NameError`). |
| `InjectionCycleError` | Constructor resolution loops back on an adapter already under construction. A loop through a `SINGLETON` is found before anything is built. |

A few mistakes are caught by plain Python exceptions instead: an invalid environment name (one that
is not a `str` included), `lifecycle` string or `@Invert(bootstrap=...)` spelling raises
`ValueError`; bare `@Invert`, the `@Invert` shape mistakes listed under
[the contract](#the-invert-contract-in-full), an adapter key that is not a `str` (in `@Adapter`,
`@Invert(keys=...)` or `Harness.override`; a `StrEnum` member is one), too many positional
arguments to an `@Invert` constructor or function, a positional-only port on an adapter constructor
and `Idunn(...)` with arguments raise `TypeError`; and a discovery root that will not import raises
its own import error. Every Idunn message names the culprit as `module.QualName`, so two `Feast`s in
two modules are never confused.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Limitations and non-features

The limitations are prices paid for a single process-wide container:

- **One container per process.** There is no second, independent `Idunn()`.
- **Thread-safety, with fine print.** Wiring is meant to happen once, at startup, but first use in
  a web worker is concurrent whatever the startup script intended, so every piece is safe to hit
  from many threads:
  - *Registration* is copy-on-write: a batch swaps in a whole new catalog under one lock, and
    readers never lock and never see half a registration.
  - *`bootstrap`* runs one discovery per root and holds no lock while modules import, so it is
    safe from any thread, during an import included. `@Invert(bootstrap=...)` calls the same
    method, so it is exactly as safe.
  - *Each `SINGLETON` is built once.* A first build takes a lock of that adapter's own and checks
    the cache again inside it, so racing threads get one instance between them. The warm path is a
    dictionary lookup with no lock, and unrelated singletons never wait on each other.
  - *A dependency cycle between singletons raises `InjectionCycleError` before any lock is taken*,
    even when two threads race it, so it can never turn into two threads each holding half of it.

  The fine print, stated plainly:
  - `reset()` is test tooling for one thread. A build racing it finishes into the generation it
    started in and is forgotten with it, but do not reset under live traffic.
  - A singleton constructor holds its lock until it returns. If it imports modules or calls
    `bootstrap`, and another thread is importing a module that needs that same singleton, the two
    can deadlock. Build-once leaves no way round that, so keep imports out of constructors.
  - For the same reason, a constructor must never wait on another thread that needs the very
    singleton being built.
  - Building an `@Invert(bootstrap=...)` consumer counts as calling `bootstrap`. Built inside a
    singleton's constructor with a port left to inject, it bootstraps under that singleton's lock
    whenever its root is not cached yet, so the import warning two points up applies. Bootstrap the
    root before the singleton's first build, or hand the consumer its ports. The resolver itself
    never sets one off: building an adapter as a dependency supplies every port.
  - An `@Invert()` consumer created *inside* a constructor while a singleton is being built (in
    the singleton's own constructor or a `TRANSIENT`'s beneath it) is part of that build: it
    picks up the path at the innermost singleton, so a loop through it raises
    `InjectionCycleError`, on one thread or two, instead of recursing or deadlocking. A loop made
    only of `TRANSIENT`s, closed by a consumer built inside one of their constructors, still ends
    in `RecursionError`. No lock is involved there, so it cannot hang, and the graph is broken
    either way.
  - Free-threaded builds (3.13t, 3.14t) should be fine, since the design leans only on atomic
    reference reads and single dictionary operations, but CI does not run one.
- **Test isolation is your job,** with help: `reset()` and `idunn.testing`. See
  [Testing](#testing).

The non-features are deliberate, so there is no point hunting for them:

- **No public `resolve()`.** Resolving by hand invites container code into business logic. The only
  construction trigger is an `@Invert()` constructor or function; resolution still happens inside
  it. And no public register: `idunn.testing` installs and overrides only for one block (or one
  decorated function), undone on exit, and nothing outside tests has any reason to import it.
- **No lifecycle on `@Invert`.** Lifecycle belongs to the provider, `@Adapter`, the single source of
  truth for a binding.
- **No priority or fallback ordering.** The only disambiguators are `key` and `envs`; overlaps fail
  loud with `InvalidAdapterError`.
- **No value or configuration injection.** Only `@Port`-typed parameters are injected. Plain values
  come from the caller.
- **No field or setter injection.** Ports arrive as constructor or function parameters, nowhere
  else.
- **No YAML, no scanning outside the root, no subclass scanning, no "name ends in `Adapter`"
  guessing, no implicit protocol matching, and no construction during decoration or discovery.** If
  an adapter wants in, it wears the badge.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Maintainer notes

The implementation is intentionally class-heavy: all three decorators are classes (`Port` via
`__new__`, `Adapter` and `Invert` via `__init__` plus `__call__`), support behavior lives in
classes, there are no loose module-level functions, and every method has a single return point,
guard clauses aside. The four layers (`app`, `domain`, `internal`, `util`) and their allowed import
directions are enforced by `tests/test_architecture.py`, along with a fifth package, `testing`: it
holds only the barrel that re-exports `Harness` from `app`, may import `app` alone, and no layer may
import it, so production code cannot lean on test tooling even by accident. The same file fails any
module import cycle in `idunn/` or `examples/`, and, inside the package, a `..` relative import, a
module path (`from idunn.domain import catalog` counts) or the root barrel, through which a back
edge would otherwise slip past the matrix unseen. For a class-by-class map of the package see
[`classes.md`](./classes.md).

### Running Idunn's own suite

Day to day, `poetry run pytest` runs everything on the development interpreter, 3.13.16 in the
in-project `.venv`. The end-to-end files, `tests/test_integration.py` (the public API over
generated packages) and `tests/test_examples.py`, carry the `integration` marker; the discovery
and bootstrap tests write packages too, but each pins one rule, so they count as unit tests. The
examples test runs every example as a script once per name on its docstring's `Environments:`
line, against `expected.<name>.txt` (`unset` means no `IDUNN_ENV`, against `expected.txt`), fails
on a missing or stray expected file, and checks discovery against its `Registers:` line, which
names classes relative to the example package (`shop.till.Till`), so a class that moves module
fails too. `bin/devtool` wraps the lot, from any directory in the repository:

```bash
poetry run bin/devtool test lint          # Ruff's linter and formatter, then mypy; --fix to rewrite
poetry run bin/devtool test unit          # everything not marked integration
poetry run bin/devtool test integration   # only the integration marker
poetry run bin/devtool test all           # lint, then everything on 3.13.16 and on Python 3.14
```

`test all` lints first, then runs the suite twice on purpose. Python 3.14 defers annotations
(PEP 649), so two `@Invert` contract tests, an unquoted forward reference with no
`from __future__ import annotations` and the shape checks that must never evaluate a hint, only
mean anything there; on older interpreters they skip, and a green 3.13 run would never notice them
breaking. So after the poetry run, `test all` picks the newest CPython 3.14.x that pyenv has
(free-threaded builds aside, and installing pyenv's latest 3.14 if there is none), keeps a venv for
it in the git-ignored `tmp/venv-3.14` (rebuilt when its interpreter differs, reinstalled when
`pyproject.toml` changes, and spared by `bin/devtool build clean`, which empties the rest of
`tmp/`), and runs the suite again with the same `-k`, `-sv` and `-n` options; coverage belongs to
the poetry run alone. Each interpreter's verdict is printed on its own line, as is lint's, and any
one failing fails the command.

CI goes wider: a `quality` job runs once on 3.13.16 (`poetry check --lock`, format, lint and
strict mypy), and a `test` job runs pytest on 3.11, 3.12, 3.13.16 and 3.14. Before calling a
change done, run the same gate locally:

```bash
poetry check --lock
poetry run bin/devtool test all
```

Every thread a test starts goes through `Racer` (`tests/_support.py`): daemon threads that share one
deadline, with any thread still alive after it recorded as a `TimeoutError`, so a deadlock fails the
test instead of hanging the suite until someone notices it is lunchtime. `run` releases its targets
together behind one barrier, `start` and `join` let a test stagger them, and `call` runs a single
call that might hang, such as a bootstrap-gate call a regression could park forever on the main
thread. A loop that never waits slips past `Racer`, so `pytest-timeout` (`timeout = 120` in
`pyproject.toml`, clear of the 60 seconds an example subprocess may take) fails any test still
running after two minutes. The `eager_switching` fixture sets `sys.setswitchinterval(1e-6)` for
races the GIL would otherwise hide. A race that passed once has merely not been caught yet, so run
the concurrency tests ten times per interpreter before calling them green:

```bash
for _ in $(seq 10); do
  poetry run pytest -q tests/test_concurrency.py tests/test_catalog.py tests/test_injection.py \
    tests/test_harness.py tests/test_bootstrap.py tests/test_bootstrap_gate.py \
    tests/test_invert_bootstrap.py
done
```

On 3.14, swap `poetry run pytest` for `tmp/venv-3.14/bin/python -m pytest`, which `test all` keeps
ready.

The suite tests through the same doors users have where it can: `@Invert()` integration tests
install adapters with `Harness`. Where the facade deliberately has no door, `tests/_support.py`
keeps a few seams: `Wiring`, a standalone mapper plus resolver; `Resolve.port(...)`, which builds
one port through the facade's private door; `PackageWriter`, for throwaway packages to discover;
and `Racer`.

### Images

`docs/images/` holds six images, and the docs use two of them. The other four are brand assets,
kept on purpose though no page references them, so an unreferenced image there is not litter. Two
file names promise sizes the files do not have; the table gives the real ones.

| File | Pixels, bytes | Shows | Used |
|---|---|---|---|
| `idunn-apple-square-50.png` | 50 x 50, 6.4 KiB | The golden apple, a knotwork heart on its face and two leaves on the stem. | The separator between `##` sections in the README and the docs. |
| `idunn-landscape-2560x900.png` | 2172 x 724, 1.9 MiB | A banner: the apple and the `idunn` wordmark on a dark panel with a gold knotwork border, flanked by four round icons (a cube, a gear, `</>` and a database). | The header at the top of the README, ABOUT and this file. |
| `idunn-apple-square-800.png` | 800 x 800, 645 KiB | The same apple as the separator, large. | Kept as a brand asset. |
| `idunn-logo-figure.png` | 1100 x 1400, 3.4 MiB | An illustrated portrait: a woman with long golden hair holds a glowing apple aloft and a basket of apples, beside a standing stone carved with the apple, the four icons on a small tree and the `idunn` wordmark, in a gold frame. | Kept as a brand asset. |
| `logo-mountain-1600x900.png` | 1672 x 941, 2.5 MiB | The apple in a ring of runes above the four icons on a branching line, the `idunn` wordmark beside it, over a night sky with mountains and pines, in a gold knotwork border. | Kept as a brand asset. |
| `logo-square-1200.png` | 1200 x 1200, 2.3 MiB | A square badge: the apple over a faint ring of runes, the four icons beneath it and the `idunn` wordmark below, on a dark rounded square with gold knotwork corners. | Kept as a brand asset. |

### Releasing

Before a release, check `authors`, the project URLs and the classifiers in `pyproject.toml`, and
give the release its entry in [`CHANGELOG.md`](../CHANGELOG.md). What changed, breaking or not, is
written down there once, so these notes do not keep a second copy to fall out of date. The README's
links are absolute `https://github.com/terracoil/idunn/...` URLs, because the README is the PyPI
long description and a relative link there leads nowhere; links inside `docs/` stay relative. Then:

```bash
poetry build
poetry publish
```
