# Idunn Advanced Notes

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-landscape-2560x900.png)

The [README](../README.md) covers normal usage: three decorators, one discovery call, one adapter per
port. This document holds everything else: choosing between adapters, the full `@Invert` contract,
discovery options, inspection, testing, the exceptions, and the lines Idunn will not cross.

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
| Config files, global scanning, name-based guessing? | No. |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## When resolution happens

Decorators construct nothing. `@Port` and `@Adapter` attach metadata; `@Invert()` wraps a
constructor. Discovery imports the bounded modules so the decorators run, then registers the decorated
classes; it constructs nothing either. Apples are catalogued at discovery and picked at construction.

Construction fires when an `@Invert()`-decorated object is built:

```python
feast = Feast(host='Bragi')  # @Invert resolves Feast's @Port parameters, then runs __init__
```

At that moment Idunn:

1. selects the active adapter for each `@Port`-typed parameter;
2. inspects that adapter's constructor and recursively resolves its own `@Port` parameters;
3. instantiates dependencies first, then the adapter, and checks the instance satisfies the port;
4. caches `SINGLETON` instances and rebuilds `TRANSIENT` ones each time;
5. assigns each resolved value to `self.<name>` on the consumer.

Dependency order is handled at resolution time, not registration time, so registration order never
matters. Two adapters that depend on each other raise `InjectionCycleError`.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## The `@Invert` contract in full

```python
@Invert()  # infer ports from the constructor's type hints
@Invert(keys={'basket': 'wild'})  # pick keyed adapters per parameter
@Invert({'basket': AppleBasketPort})  # explicit param -> port, for an un-annotated parameter
```

- **It assigns `self.<name>`** for every injected port parameter and forwards the value into the
  wrapped `__init__` body, so the body can use the parameter normally.
- **A caller-supplied argument always wins.** Passing the parameter explicitly skips injection for
  it, which keeps the class trivially testable.
- **Resolution is recursive.** If the chosen adapter's own constructor takes `@Port` parameters,
  those resolve first, all the way down.
- **Optional dependencies.** A parameter typed `SomePort | None`, or any `@Port` parameter with a
  default, is optional: when no adapter is active it receives the default, or `None`, instead of
  raising `AdapterNotFoundError`. The same rule applies inside an adapter's own constructor.
- **Keyed selection at the point of use.** `keys={'param': 'name'}` picks a keyed adapter where it
  is consumed rather than in a container call elsewhere. Keys apply only at `@Invert()` consumers;
  an adapter's own dependencies always resolve unkeyed.
- **Explicit mapping.** `@Invert({'param': SomePort})` injects a parameter that has no annotation.
- **Parentheses are required.** `Invert` is a class; applying it bare raises `TypeError`.

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

When the same role needs different implementations in dev, test, and production, put the environment
in the decorator. The adapters are never active at once, so an unkeyed resolve still has exactly one
answer and the consumer never changes.

```python
@Adapter(PaymentPort, envs={'prod'})
class StripePaymentAdapter(PaymentPort): ...


@Adapter(PaymentPort, envs={'test', 'ci'})
class FakePaymentAdapter(PaymentPort): ...
```

| `envs=` | Active when |
|---|---|
| `None` (default) | Every environment. |
| `{'test'}` | The active environment is `test`. |
| `{'test', 'ci'}` | The active environment is `test` or `ci`. |

The active environment comes from `Idunn().reset(environment=...)`, then the `IDUNN_ENV` variable,
then the default `local`. Names are lowercased with `_` turned into `-`, so `My_Env` and `my-env`
are the same place, and must match `[a-z0-9][a-z0-9.-]*`.

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
overlaps with everything. Idunn refuses to guess which apple you meant.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Discovery options

`autodiscover` and `bootstrap` share one signature:

```python
Idunn().autodiscover(
  'my_app',
  port_package_names=None,  # dotted-path parts that mark port modules; default {'port', 'ports'}
  adapter_package_names=None,  # likewise for adapters; default {'adapter', 'adapters'}
  strict=True,  # raise DiscoveryError on an unimportable module instead of skipping it
)
```

- **Naming rule.** A module qualifies when any part of its dotted path matches one of the names,
  case-insensitively. Override the names when your layout uses `contracts/` and `impl/` instead.
- **Root must be importable.** Pass the package's dotted name exactly as you would `import` it. A file
  path does not work.
- **`ReportMap`.** Both calls return a `TypedDict` of strings: `root_package`,
  `imported_port_modules`, `imported_adapter_modules`, `imported_modules`, `registered_ports`, and
  `registered_adapters`. Class names are fully qualified. Import it as `from idunn import ReportMap`
  when you annotate a stored report.
- **Multiple roots accumulate.** Registration is idempotent and the catalog is shared, so call
  discovery once per package that contributes adapters.
- **`bootstrap` caches per root.** The first call for a root discovers with the options given. Later
  calls for that root return the same report without rescanning and ignore their options. Distinct
  roots are tracked independently, the guard is locked, and `reset()` forgets the cache along with
  the registrations.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Inspecting the graph

`Idunn().describe()` renders the active port-to-adapter bindings for the current environment. It is
built from the same structured snapshot the resolver selects from, so what it prints is what an
unkeyed resolve would pick.

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

`envs=*` marks an adapter active everywhere. A port whose adapters are all keyed shows
`selected: <none>`, because nothing answers an unkeyed resolve there.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Test isolation

`Idunn` is a process-wide singleton, so tests must reset it between cases. `reset()` keeps the same
object, empties registrations, cached singleton instances, and the `bootstrap` cache, and rebinds the
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
Because a reset empties the catalog, run it before discovery, not after.

Adapters defined inside a test function are out of discovery's reach, and the facade has no public
register or resolve. Idunn's own suite drives the internal engine through two seams in
`tests/_support.py`: `Wiring`, a standalone mapper plus resolver, and `Container.install(...)`, which
pushes adapters into the singleton for `@Invert()` tests.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Exceptions

All inherit from `IdunnError` and import from `idunn`:

| Class | Raised when |
|---|---|
| `InvalidPortError` | `@Port` is applied to a non-Protocol, or an adapter names an unmarked port. |
| `InvalidAdapterError` | `@Adapter` is applied to a non-class, two adapters collide, or a built instance does not satisfy its port. |
| `AdapterNotFoundError` | No active adapter exists for a requested port and the parameter is not optional. |
| `DiscoveryError` | A bounded module fails to import and `strict=True`. |
| `MissingTypeHintError` | An adapter constructor parameter has no type hint, or is not a port and has no default. |
| `InjectionCycleError` | Constructor resolution loops back on an adapter already under construction. |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Limitations and non-features

The limitations are prices paid for a single process-wide container:

- **One container per process.** There is no second, independent `Idunn()`.
- **Not thread-safe.** Only the `bootstrap` guard is locked. Wire everything on one thread at
  startup, then resolve.
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
- **No YAML, no package-wide or subclass scanning, no "name ends in `Adapter`" guessing, no implicit
  protocol matching, and no construction during decoration or discovery.** If an adapter wants in, it
  wears the badge.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Maintainer notes

The implementation is intentionally class-heavy: all three decorators are classes (`Port` via
`__new__`, `Adapter` and `Invert` via `__init__` plus `__call__`), support behavior lives in classes,
there are no loose module-level functions, and every method has a single return point. The four
layers (`app`, `domain`, `internal`, `util`) and their allowed import directions are enforced by
`tests/test_architecture.py`.

Before a release, check `authors`, the project URLs, and the classifiers in `pyproject.toml`, then:

```bash
poetry build
poetry publish
```

For a class-by-class map of the package see [`classes.md`](./classes.md).
