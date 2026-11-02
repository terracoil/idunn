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
- [Test isolation](#test-isolation)
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
| Receive dependencies? | Decorate the consumer's `__init__` with `@Invert()`. |
| Register everything? | `Idunn().autodiscover('my_app')` once at startup, or `Idunn().bootstrap('my_lib')` from a library's entry points. |
| Does `@Adapter` make the class implement the port? | No. The class must satisfy the Protocol itself. |
| When is injection done? | When an `@Invert()` constructor runs. Never at decoration or discovery. |
| Several adapters for one port? | `envs=` separates them by environment; `key=` makes one opt-in. |
| Optional dependency? | Type the parameter `SomePort \| None`, or give it a default. |
| Field, setter, or value injection? | No. Constructor-time ports only. |
| Config files, scanning outside the root, name-based guessing? | No, no, and no. |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## When resolution happens

Decorators construct nothing. `@Port` and `@Adapter` attach metadata; `@Invert()` wraps a
constructor. Discovery imports the modules under the root so the decorators run, then registers the
decorated classes; it constructs nothing either. Apples are catalogued at discovery and picked at
construction, never the other way round.

Construction fires when an `@Invert()`-decorated object is built:

```python
feast = Feast(host='Bragi')  # @Invert resolves Feast's @Port parameters, then runs __init__
```

At that moment Idunn:

1. selects the active adapter for each `@Port`-typed parameter the caller did not supply;
2. inspects that adapter's constructor and recursively resolves its own `@Port` parameters;
3. instantiates dependencies first, then the adapter, and checks the instance satisfies the port;
4. caches `SINGLETON` instances and rebuilds `TRANSIENT` ones each time (`lifecycle=` also accepts
   the lowercase strings `'singleton'` and `'transient'`);
5. assigns every port parameter to `self.<name>` on the consumer, then runs the body.

Dependency order is worked out at resolution time, not registration time, so registration order
never matters. Two adapters that depend on each other raise `InjectionCycleError`, which is kinder
than the alternative.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## The `@Invert` contract in full

```python
@Invert()  # infer ports from the constructor's type hints
@Invert(keys={'basket': 'wild'})  # pick keyed adapters per parameter
@Invert({'basket': AppleBasketPort})  # explicit param -> port, for an un-annotated parameter
```

- **It assigns `self.<name>`** for every port parameter, injected or caller-supplied, before the
  wrapped body runs, and forwards the same value into the body as a normal argument.
- **A caller-supplied argument always wins.** Passing the parameter skips injection for it, which
  keeps the class trivially testable.
- **Pass plain arguments by keyword.** A positional argument fills the next parameter whether it is
  a port or not: with `__init__(self, basket: AppleBasketPort, host: str)`, `Feast('Bragi')` binds
  `'Bragi'` to `basket` and then raises `TypeError` about the missing `host`. Either pass plain
  values by keyword or declare port parameters last.
- **Resolution is recursive.** If the chosen adapter's own constructor takes `@Port` parameters,
  those resolve first, all the way down.
- **Optional dependencies.** A parameter typed `SomePort | None`, or any `@Port` parameter with a
  default, is optional: when no adapter is active it receives the default, or `None`, instead of
  raising `AdapterNotFoundError`. The same rule applies inside an adapter's own constructor.
- **Keyed selection at the point of use.** `keys={'param': 'name'}` picks a keyed adapter where it
  is consumed rather than in a container call elsewhere. Keys apply only at `@Invert()` consumers;
  an adapter's own dependencies always resolve unkeyed, so a keyed adapter never sneaks into
  someone else's constructor.
- **Explicit mapping.** `@Invert({'param': SomePort})` injects a parameter whose annotation is
  missing or is not a port.
  If the parameter is annotated with a `@Port` as well, the annotation wins and the map entry is
  ignored: the hint is the contract, the map is a fallback for when there is no hint.
- **Parentheses are required.** `Invert` is a class; applying it bare raises `TypeError` at
  decoration rather than something stranger later.

```python
class Service:
  @Invert()
  def __init__(self, logger: LoggerPort | None = None) -> None:
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
  def __init__(self, notifier: NotifierPort) -> None:
    pass
```

If `email` and `sms` are the only adapters for `NotifierPort`, a plain `@Invert()` parameter typed
`NotifierPort` raises `AdapterNotFoundError`: there is no unkeyed apple in the basket. Pick one with
`keys=`, or register an unkeyed adapter as the default.

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
an overlapping environment raise `InvalidAdapterError` at registration. An env-agnostic adapter
overlaps with everything. Idunn refuses to guess which apple you meant, and refuses at startup
rather than at the first unlucky request.

Two `@Adapter` lines on one class collide sooner still: the second raises `InvalidAdapterError` at
import, because only one declaration could ever win, so one of the two lines was always wrong. A
subclass may wear its own `@Adapter`; it is a different class and registers as one, while an
undecorated subclass stays invisible to discovery.

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
  under the root, or `'legacy'` for the whole subtree. The root's own name never matches, so to discover in-package test fakes on purpose, make
  the test package the root: `autodiscover('my_app.tests')`.
- **`strict`.** All modules import before anything registers, so with `strict=True` an unimportable
  module raises `DiscoveryError` naming it and leaves the catalog untouched; `bootstrap` does not
  cache the failure. With `strict=False` the module is skipped and listed in `skipped_modules`. Only
  `Exception` is caught: a module that calls `sys.exit()` or parses `argv` at import raises
  `SystemExit`, which is not swallowed. Prefer `exclude` for such modules. Registration, unlike
  importing, is not all-or-nothing: if two adapters collide, the `InvalidAdapterError` propagates
  and whatever registered before it stays registered.
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
  last two list only the classes *this call* registered, so a repeat run reports none. Class names
  are fully qualified. Import it as `from idunn import ReportMap` when you annotate a stored report.
- **Multiple roots accumulate.** Registration is idempotent and the catalog is shared, so call
  discovery once per package that contributes adapters. Each root registers only the classes defined
  under it.
- **`bootstrap` caches per root.** The first call for a root discovers with the options given. Later
  calls for that root return the same report without rescanning and ignore their options. Distinct
  roots are tracked independently, the guard is locked, failures are not cached, and `reset()`
  forgets the cache along with the registrations.
- **Re-entrant `bootstrap`.** A module under the root may call `bootstrap` for that root while it is
  being imported. The nested call finishes first and its report is the one cached, so a class the
  module defines *after* that call is registered but missing from the report. Put the call at the
  end of the module, or trust `describe()`, which is authoritative.

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
  - my_app.adapters.stripe.StripePaymentAdapter key=None envs=prod singleton
  - my_app.adapters.fake.FakePaymentAdapter key=None envs=ci,test
```

`envs=*` marks an adapter active everywhere. A port with no active unkeyed adapter shows
`selected: <none>`: its adapters may all be keyed, all belong to other environments, or not exist
yet.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Test isolation

`Idunn` is a process-wide singleton, so tests must reset it between cases. `reset()` keeps the same
object, empties registrations, cached singleton instances and the `bootstrap` cache, and rebinds the
environment:

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

Adapters defined inside a test function are out of discovery's reach, and the facade has no public
register or resolve. Idunn's own suite drives the internal engine through two seams in
`tests/_support.py`: `Wiring`, a standalone mapper plus resolver, and `Container.install(...)`,
which pushes adapters into the singleton for `@Invert()` tests.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Exceptions

All inherit from `IdunnError` and import from `idunn`, so one `except IdunnError` covers every
class below:

| Class | Raised when |
|---|---|
| `InvalidPortError` | `@Port` is applied to anything but a Protocol (`Port(5)` included), an adapter names an unmarked port, or a non-port is resolved (say, through an explicit `@Invert` map). |
| `InvalidAdapterError` | `@Adapter` is applied to a non-class or twice to one class, two adapters collide, or a built instance does not satisfy its port. |
| `AdapterNotFoundError` | No active adapter exists for a requested port and the parameter is not optional. |
| `DiscoveryError` | A module below the discovery root fails to import and `strict=True`, or the root package does not live in a directory (a zip, say), whatever `strict` says. |
| `MissingTypeHintError` | An adapter constructor parameter without a default has no annotation, or one that is not a port. |
| `InjectionCycleError` | Constructor resolution loops back on an adapter already under construction. |

A few mistakes are caught by plain Python exceptions instead: an invalid environment name or
`lifecycle` string raises `ValueError`, bare `@Invert` and `Idunn(...)` with arguments raise
`TypeError`, and a discovery root that will not import raises its own import error. Every Idunn
message names the culprit as `module.QualName`, so two `Feast`s in two modules are never confused.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Limitations and non-features

The limitations are prices paid for a single process-wide container:

- **One container per process.** There is no second, independent `Idunn()`.
- **Not thread-safe.** Only creating the singleton and the `bootstrap` guard are locked. The catalog
  and the singleton cache are plain, unlocked state, because wiring is meant to happen once, on one
  thread, at startup. Do that, then resolve; two threads racing to build the same `SINGLETON` for
  the first time may each walk away with their own.
- **Test isolation is your job.** See [above](#test-isolation).

The non-features are deliberate, so there is no point hunting for them:

- **No public `resolve()`.** Resolving by hand invites container code into business logic. The only
  construction trigger is an `@Invert()` constructor; resolution still happens inside it.
- **No lifecycle on `@Invert`.** Lifecycle belongs to the provider, `@Adapter`, the single source of
  truth for a binding.
- **No priority or fallback ordering.** The only disambiguators are `key` and `envs`; overlaps fail
  loud with `InvalidAdapterError`.
- **No value or configuration injection.** Only `@Port`-typed parameters are injected. Plain values
  come from the caller.
- **No field or setter injection.** Constructor-time only.
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
directions are enforced by `tests/test_architecture.py`.

Before a release, check `authors`, the project URLs and the classifiers in `pyproject.toml`. Then:

```bash
poetry build
poetry publish
```

For a class-by-class map of the package see [`classes.md`](./classes.md).
