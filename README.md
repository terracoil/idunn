# Idunn 🍎

**Idunn** is a tiny Python dependency-inversion / IoC toolkit built around **constructor-time
injection only** — small enough to read on a coffee break, opinionated enough to keep your wiring
honest.

![Idunn](https://github.com/terracoil/idunn/blob/master/docs/images/idunn-ls.png)

> *"Everything should be made as simple as possible, but not simpler."* — Albert Einstein

The name comes from **Iðunn / Idunn**, the Norse keeper of the apples that keep the gods young.
Idunn borrows that image as its DI metaphor: keep the right dependencies close to the system and the
code stays fresh, instead of hardening into the kind of brittle wiring that makes future-you
sigh. ✨

> 📖 **New to Idunn?** Read **[About Idunn](./docs/ABOUT.md)** — the philosophy, the
> Port → Adapter → `@Invert` model, and why the short "no" list *is* the feature. Then come
> back here for the reference.

# 📚 Table-of-Contents

- [The whole API 🎟️](#the-whole-api-)
- [The three decorators 🍎](#the-three-decorators-)
  - [`@Port` 🔌](#port-)
  - [`@Adapter` 🧩](#adapter-)
  - [`@Invert` 🪄](#invert-)
- [Quick-start Guide 🌱](#quick-start-guide-)
- [Design stance 🧭](#design-stance-)
- [Install locally 📦](#install-locally-)
- [Basic usage 🪄](#basic-usage-)
- [Recommended application layout 🌳](#recommended-application-layout-)
- [AutoDiscovery rule 🔍](#autodiscovery-rule-)
- [Port implementation rule 🔌](#port-implementation-rule-)
- [Mapping adapters to ports 🍎](#mapping-adapters-to-ports-)
  - [With no parameters](#with-no-parameters)
  - [Via the environment](#via-the-environment)
  - [Environment matching rules](#environment-matching-rules)
  - [Via keys](#via-keys)
  - [Same key, different environments](#same-key-different-environments)
- [Lifecycles 🔄](#lifecycles-)
- [Known limitations 🚧](#known-limitations-)
- [Development workflow 🧪](#development-workflow-)
- [What Idunn intentionally does not do 🚫](#what-idunn-intentionally-does-not-do-)
- [Going further 📒](#going-further-)
- [Code style constraints 📐](#code-style-constraints-)
- [Version target 🐍](#version-target-)
- [Before publishing to PyPI 🏁](#before-publishing-to-pypi-)

## The whole API 🎟️

Everything you import lives at the top level of the `idunn` package — you never reach into
sub-packages:

```python
from idunn import Port, Adapter, Invert     # the three decorators
from idunn import Idunn                      # the container (you touch it once: autodiscover)
from idunn import LifecycleEnum              # passed to @Adapter
from idunn import IdunnError                 # base of the exception hierarchy you catch
```

That's the entire surface: **three decorators**, the **`Idunn().autodiscover(...)`** bootstrap call,
`LifecycleEnum`, and the [exceptions](#exceptions). Registration, selection and construction all
happen behind the container — see [`docs/ADVANCED.md`](./docs/ADVANCED.md) if you ever want to peek.

## The three decorators 🍎

Idunn is *just* these three decorators. Define a contract, bind an implementation, receive it — no
container code in sight.

### `@Port` 🔌

```python
def Port(cls: T) -> T
```

Marks a `typing.Protocol` as an injectable **contract**. Applied to anything that is not a
`Protocol`, it raises `InvalidPortError`. The decorated protocol is made `runtime_checkable` so
Idunn can verify that an adapter actually satisfies it.

```python
from typing import Protocol
from idunn import Port


@Port
class AppleBasketPort(Protocol):
    def take_apple(self) -> str: ...
```

### `@Adapter` 🧩

```python
def Adapter(
    port: type,
    *,
    key: str | None = None,
    lifecycle: LifecycleEnum | str = LifecycleEnum.TRANSIENT,
    envs: Iterable[str] | str | None = None,
) -> Callable[[T], T]
```

Declares a concrete class as an **implementation** of `port`. It attaches metadata and constructs
nothing.

| Parameter | Meaning |
|---|---|
| `port` | The `@Port` this class implements (must be marked, else `InvalidPortError`). |
| `key` | Omit it and the adapter is **unkeyed** — it answers an ordinary resolve / plain `@Invert`. Give it a `key` and the adapter is **opt-in**: reachable only by that key, never by an unkeyed resolve. |
| `lifecycle` | `TRANSIENT` (default — new instance each time) or `SINGLETON` (built once, reused). |
| `envs` | Environments the adapter is active in. `None` = every environment. See [environment matching](#environment-matching-rules). |

```python
from idunn import Adapter, LifecycleEnum


@Adapter(AppleBasketPort, lifecycle=LifecycleEnum.SINGLETON)
class GoldenAppleBasketAdapter(AppleBasketPort):
    def take_apple(self) -> str:
        return "🍎 youth restored"
```

The class must satisfy the protocol structurally or by inheritance — `@Adapter` never synthesizes or
mutates it. Exactly one *unkeyed* adapter may be active per port in any environment.

### `@Invert` 🪄

```python
@Invert                                   # infer ports from the constructor's type hints
@Invert(keys={"basket": "wild"})          # pick keyed adapters per parameter
@Invert({"basket": AppleBasketPort})      # explicit param -> port (for an un-annotated parameter)
```

Wraps a **consumer's `__init__`**. Every parameter whose type hint is a `@Port` is resolved from the
process-wide `Idunn()` container *when the constructor runs* and assigned to `self.<name>`. This is
the only sanctioned way to start an object graph — you construct your entry object and the rest wires
itself; you never call the container to resolve.

The full contract:

- **It assigns `self.<name>`** for every injected port parameter, *and* forwards the resolved value
  into the wrapped `__init__` body — so the body can use the parameter normally.
- **A caller-supplied argument always wins.** `Feast(basket=my_test_basket)` skips injection for
  `basket`, which keeps the class trivially testable.
- **Resolution is recursive.** If the injected adapter's own constructor takes `@Port` parameters,
  those are resolved first.
- **Optional dependencies.** A port parameter typed `SomePort | None` (or any `@Port` parameter that
  has a default value) is *optional*: if no adapter is active, the default — or `None` — is used
  instead of raising. The same rule applies inside an adapter's own constructor, not just at the
  `@Invert` consumer boundary.
- **Keyed selection at the point of use.** `@Invert(keys={"param": "name"})` picks a keyed adapter
  right where it is consumed, rather than in a container call elsewhere.

```python
from idunn import Invert


class Feast:
    basket: AppleBasketPort                 # declared for the type checker; @Invert assigns it

    @Invert
    def __init__(self, basket: AppleBasketPort, other: str) -> None:
        self.other = other                  # self.basket is injected and assigned for you

    def serve(self) -> str:
        return f"{self.other}: {self.basket.take_apple()}"
```

## Quick-start Guide 🌱

Idunn is published on [PyPI](https://pypi.org/project/idunn/). Install it with pip:

```bash
pip install idunn
```

(Using Poetry? `poetry add idunn`.)

> `idunn` (lowercase) is the package you install; `Idunn` (capital-I, the class) is the one
> process-wide container you import from it. `Idunn()` always hands back that same shared container —
> call it a thousand times and you still get the one barrel of apples.

Mark a **port** and an **adapter** in modules named `ports` / `adapters`, decorate the consumer with
`@Invert`, let Idunn discover everything once at startup, then just construct your entry object:

```python
from idunn import Idunn

Idunn().autodiscover("my_app")     # import & register every @Port/@Adapter under my_app
app = MyApp()                      # MyApp.__init__ is @Invert-decorated; its ports wire themselves
app.run()
```

`autodiscover` is the only registration step you need, and `@Invert` is the only wiring step. A
runnable copy lives in `examples/` (`python -m examples.basic_usage`).

## Design stance 🧭

| Question | Idunn answer |
|---|---|
| How do I define a dependency? | Create a `Protocol` and mark it with `@Port`. |
| How do I bind behavior? | Mark a concrete class with `@Adapter(...)`. |
| How do I receive dependencies without container code? | Decorate the consumer's constructor with `@Invert`. |
| How do I register everything? | `Idunn().autodiscover("my_app")` once at startup. |
| Does `@Adapter` make the class implement the port? | No. The class must satisfy the `Protocol`, structurally or by inheritance. |
| When are dependencies injected? | When an `@Invert`-decorated constructor is called. |
| Optional dependency? | Type the parameter `SomePort | None` (or give it a default). |
| Field injection? | No. |
| Setter injection? | No. |
| External YAML config? | No. |
| Implicit protocol matching? | No. |
| Auto-discovery? | Yes, but only for decorated ports/adapters inside packages or modules named `port`, `ports`, `adapter`, or `adapters`. |
| Multiple adapters? | `envs` separates them per environment; `key` makes one opt-in. |
| Environments? | `IDUNN_ENV`, plus decorator-local `envs={...}`. |
| Tooling? | Poetry, pytest, Ruff, and Mypy are configured in `pyproject.toml`. |

## Install locally 📦

```bash
poetry install --with dev
```

## Basic usage 🪄

The headline workflow is **decorator-only**: mark ports and adapters, mark consumer constructors
with `@Invert`, discover once, then construct. Normal code never touches the container.

```python
from typing import Protocol

from idunn import Adapter, Idunn, Invert, LifecycleEnum, Port


@Port
class AppleBasketPort(Protocol):
    def take_apple(self) -> str: ...


@Adapter(AppleBasketPort, lifecycle=LifecycleEnum.SINGLETON)
class GoldenAppleBasketAdapter(AppleBasketPort):
    def take_apple(self) -> str:
        return "🍎 youth restored"


class Feast:
    basket: AppleBasketPort                # declared for the type checker; @Invert assigns it

    @Invert
    def __init__(self, basket: AppleBasketPort, other: str) -> None:
        self.other = other                 # self.basket is injected and assigned for you

    def serve(self) -> str:
        return f"{self.other}: {self.basket.take_apple()}"


Idunn().autodiscover("my_app")             # one-time bootstrap (ports/adapters live in my_app)
feast = Feast(other="funky")               # basket is resolved & injected automatically
print(feast.serve())                       # funky: 🍎 youth restored
```

`@Invert` inspects the constructor's type hints; every parameter annotated with a `@Port` is resolved
from the `Idunn()` singleton at construction time and assigned to `self.<name>`. A caller-supplied
argument always wins (`Feast(basket=my_basket, other="x")`), so the class stays trivially testable —
handy when you'd rather hand it a paper bag of test apples than the real basket. Power users can
target a keyed adapter with `@Invert(keys={"basket": "golden"})`, or inject an unannotated parameter
with an explicit map: `@Invert({"basket": AppleBasketPort})`.

## Recommended application layout 🌳

Idunn can discover decorated ports and adapters automatically, but if you are using IoC, you are interested in structure.

```text
my_app/
  __init__.py
  domain/
    ports/
  infrastructure/
    adapters/
      __init__.py
      apples.py
      payments.py
  billing/
    ports.py
    adapters/
      __init__.py
      stripe.py
```

Then at startup:

```python
from idunn import Idunn

Idunn().autodiscover("my_app")
app = MyApp()      # the @Invert-decorated entry object pulls in everything it needs
```

`Idunn().autodiscover("my_app")` imports modules whose dotted names contain one of these exact
parts:

```text
port
ports
adapter
adapters
```

Ports are imported and registered first; adapters second. It does **not** import arbitrary modules
just because they live inside your app, and it does **not** register undecorated classes. Discovery
is a metal detector tuned to one shape of badge, not a vacuum cleaner.

## AutoDiscovery rule 🔍

Good:

```python
@Port
class AppleBasketPort(Protocol):
    def take_apple(self) -> str: ...


@Adapter(AppleBasketPort)
class GoldenAppleBasketAdapter(AppleBasketPort):
    ...
```

These classes can be found by discovery because they wear the apple badge.

Not registered:

```python
class GoldenAppleBasketAdapter(AppleBasketPort):
    ...
```

Even if the class structurally satisfies the port, Idunn ignores it unless it is marked with
`@Adapter(...)`. Looking the part is not the same as wearing the badge.

## Port implementation rule 🔌
![Idunn2](![Idunn](https://github.com/terracoil/idunn/blob/master/docs/images/idunn-logo-md.png))

Adapters must satisfy their ports. Idunn does **not** synthesize, monkey-patch, or mutate adapter
classes.

Recommended style:

```python
@Adapter(AppleBasketPort)
class GoldenAppleBasketAdapter(AppleBasketPort):
    ...
```

Also valid in Python protocol terms:

```python
@Adapter(AppleBasketPort)
class GoldenAppleBasketAdapter:
    def take_apple(self) -> str:
        return "golden apple"
```

The second form relies on structural typing. The first form is clearer, so examples use explicit
inheritance.

## Mapping adapters to ports 🍎

A port is an empty basket; an adapter is the apples you put in it. How you pick between adapters
depends on how many you have. Start simple, and reach for keys only when you genuinely need them.

**The one rule:** resolving a port *without a key* only ever sees adapters registered *without a
key*. Keyed adapters are opt-in — you address them by name, or they sit quietly in the cellar.

### With no parameters

Most ports have exactly one implementation, and the calling code does not care which. Register it
plain and Idunn just hands it over — the implementation stays hidden behind the port, which is the
whole point of a port.

```python
@Adapter(AppleBasketPort)
class GoldenAppleBasketAdapter(AppleBasketPort):
    def take_apple(self) -> str:
        return "youth restored"


class Feast:
    basket: AppleBasketPort  # assigned by @Invert

    @Invert
    def __init__(self, basket: AppleBasketPort) -> None:
        pass


Idunn().autodiscover("my_app")
Feast().basket.take_apple()
```

One basket, one adapter, zero decisions. This is the case you want most of the time.

### Via the environment

When the *same role* needs *different apples* in dev, test, and production — a real gateway in
`prod`, a fake one in tests — put the environment right in the decorator. No config files, no YAML,
no 200-line `settings.py`. The adapters are never active at once, so an unkeyed resolve always has
exactly one answer and the consumer never changes between environments.

```python
@Adapter(PaymentPort, envs={"prod"})
class StripePaymentAdapter(PaymentPort): ...

@Adapter(PaymentPort, envs={"test", "ci"})
class FakePaymentAdapter(PaymentPort): ...
```

Set the active environment with `IDUNN_ENV`:

```bash
IDUNN_ENV=test
```

If `IDUNN_ENV` is unset, Idunn defaults to `local`. Environment names are normalized to lowercase,
and underscores become hyphens (so `My_Env` and `my-env` are the same place). In tests it's often
easier to rebind the singleton directly with `Idunn().reset(environment="prod")` — see
[`docs/ADVANCED.md`](./docs/ADVANCED.md#test-isolation).

### Environment matching rules

| Decorator value | Behavior |
|---|---|
| `envs=None` | Adapter is active in every environment (the apple for all seasons). |
| `envs={"test"}` | Adapter is active only when the active environment is `test`. |
| `envs={"test", "ci"}` | Adapter is active in either `test` or `ci`. |

### Via keys

When several implementations are *all* valid in the *same* environment and the environment can't
tell them apart, give each one a key. The cleanest way to pick one is at the point of use — the
consumer's constructor — with `@Invert(keys={...})`. The choice lives right next to the code that
depends on it.

```python
@Adapter(NotifierPort, key="email")
class EmailNotifier(NotifierPort): ...

@Adapter(NotifierPort, key="sms")
class SmsNotifier(NotifierPort): ...

class Reminder:
    notifier: NotifierPort  # assigned by @Invert

    @Invert(keys={"notifier": "sms"})
    def __init__(self, notifier: NotifierPort) -> None:
        pass
```

And the one rule again, because it earns repeating: a keyed adapter never answers an unkeyed resolve.
If `email` and `sms` are your *only* adapters for `NotifierPort`, then a plain `@Invert` parameter
typed `NotifierPort` raises `AdapterNotFoundError` — there's no unkeyed apple in the basket. Pick one
with `keys={...}`, or register an unkeyed adapter.

### Same key, different environments

A key only has to be unique *within an environment*, so the same key can name different adapters in
environments that never overlap:

```python
@Adapter(PaymentPort, key="primary", envs={"prod"})
class StripePaymentAdapter(PaymentPort): ...

@Adapter(PaymentPort, key="primary", envs={"test"})
class FakePaymentAdapter(PaymentPort): ...
```

This, however, is a collision — both are active in `prod`:

```python
@Adapter(PaymentPort, key="primary", envs={"prod"})
class StripePaymentAdapter(PaymentPort): ...

@Adapter(PaymentPort, key="primary", envs={"prod"})
class BraintreePaymentAdapter(PaymentPort): ...
```

Idunn raises `InvalidAdapterError` when two adapters share a port and key (unkeyed counts as the
same "no key") and are both active in overlapping environments. Two apples, one label, same
shelf — somebody's about to grab the wrong one, so Idunn refuses to guess.

## Lifecycles 🔄

| LifecycleEnum | Behavior |
|---|---|
| `LifecycleEnum.TRANSIENT` | A new instance is built every time the port is resolved. |
| `LifecycleEnum.SINGLETON` | One instance is created and reused. |

## Known limitations 🚧

`Idunn` is deliberately a single process-wide container, which buys simplicity at a few prices worth
knowing:

- **One container per process.** There is no second, independent container; everything shares the
  same `Idunn()`. (Multi-container setups are out of scope — one barrel of apples per kitchen.)
- **Not thread-safe.** Wire everything up at startup on one thread, *then* resolve. Registration and
  resolution mutate shared state without locking, and Idunn does not appreciate two cooks resolving
  in her kitchen at once.
- **Test isolation is your job.** Reset between tests with `Idunn().reset()` (e.g. an autouse
  fixture). See [`docs/ADVANCED.md`](./docs/ADVANCED.md#test-isolation).

## Development workflow 🧪

The project uses Poetry with pytest, Ruff, and Mypy configured in `pyproject.toml`.

```bash
poetry install --with dev
poetry run pytest
poetry run ruff format --check .
poetry run ruff check .
poetry run mypy
```

A GitHub Actions workflow is included at:

```text
.github/workflows/ci.yml
```

The CI quality gate runs the same checks across Python 3.11, 3.12, 3.13, and 3.14.

## What Idunn intentionally does not do 🚫

Half of Idunn's design is the features it cheerfully refuses to grow:

- No external YAML configuration
- No package-wide global scanning
- No subclass scanning
- No “class name ends with `Adapter`, so let’s register it” guesswork
- No implicit protocol matching for registration
- No construction during decoration
- No construction during autodiscovery
- No field injection
- No setter injection
- No loose global resolver functions

If an adapter wants in, it wears the apple badge explicitly — no badge, no basket:

```python
@Adapter(SomePort)
class SomeAdapter(SomePort):
    ...
```

That short "no" list *is* the feature. (See the Einstein quote up top: as simple as possible, and
not one apple simpler.)

## Going further 📒

The everyday API is the three decorators plus `autodiscover`. Everything else — how resolution
actually fires, inspecting the wired graph with `describe()`, manual registration, rebinding the
environment for tests, and the deliberate non-features (no lifecycle on `@Invert`, no priority,
no value injection) — lives in [`docs/ADVANCED.md`](./docs/ADVANCED.md). A class-by-class catalog is
in [`docs/classes.md`](./docs/classes.md).

### Exceptions

All inherit from `IdunnError`, and all import from `idunn`:

| Class | Raised when… |
|-------|--------------|
| `InvalidPortError` | `@Port` is applied to a non-Protocol class. |
| `InvalidAdapterError` | An adapter registration is invalid (bad target, duplicate key in overlapping environments, unsatisfied port). |
| `AdapterNotFoundError` | No active adapter is registered for a requested port. |
| `DiscoveryError` | Autodiscovery fails to import a bounded module. |
| `MissingTypeHintError` | Constructor injection needs a type hint that is missing (or a non-port param with no default). |
| `InjectionCycleError` | Constructor dependency resolution loops back on itself. |

## Code style constraints 📐

The implementation is intentionally class-heavy:

- decorators are functions because Python decorators are naturally functions;
- support behavior is encapsulated in classes;
- package code avoids loose utility functions;
- package methods/functions use a single return point.

## Version target 🐍

```toml
python = ">=3.11,<4.0"
```

## Before publishing to PyPI 🏁

Before the first public release, update these project-specific values:

- `authors` in `pyproject.toml`
- package homepage / repository URLs, once the repo exists
- the copyright holder in `LICENSE`, if needed
- package classifiers if the tested Python matrix changes

Then run:

```bash
poetry build
poetry publish
```
