# About Idunn 🍎

![Idunn](https://github.com/terracoil/idunn/blob/master/docs/images/idunn-ls.png)

> 📘 This is the *story* of Idunn — the idea, the model, and the design choices behind it.
> For the hands-on reference (every signature, every selection rule), read the
> [README](../README.md). For the engine internals, see [`ADVANCED.md`](./ADVANCED.md).

*"Everything should be made as simple as possible, but not simpler."* — Albert Einstein

Idunn is a tiny dependency-inversion toolkit for Python. You can learn the whole of it from
three decorators and one bootstrap call, and the rest of this article explains *why* it stops
there — and why that restraint is the point.

## Contents

- [The apples and the metaphor](#the-apples-and-the-metaphor)
- [A toolkit you can read in one sitting](#a-toolkit-you-can-read-in-one-sitting)
- [The Idunn model](#the-idunn-model)
  - [Ports define contracts](#ports-define-contracts)
  - [Adapters wear a badge](#adapters-wear-a-badge)
  - [`@Invert` receives dependencies](#invert-receives-dependencies)
- [A worked example](#a-worked-example)
  - [One adapter, zero decisions](#one-adapter-zero-decisions)
  - [Two adapters, one environment](#two-adapters-one-environment)
  - [The same role across environments](#the-same-role-across-environments)
  - [Optional dependencies](#optional-dependencies)
- [The features Idunn refuses](#the-features-idunn-refuses)
- [One container per process](#one-container-per-process)
- [Where to go next](#where-to-go-next)

## The apples and the metaphor

The name comes from **Iðunn**, the Norse keeper of the apples that kept the gods young. It is a
fitting image for dependency inversion: keep the right dependencies close to the system and the
code stays fresh, instead of hardening into the brittle, hand-wired tangle that makes future-you
sigh. A port is an empty basket; an adapter is the apple you put in it; a consumer simply asks
for the basket and trusts that the right apple is inside.

The metaphor is not decoration — it is the whole mental model. Once you think in baskets and
apples, the entire API follows.

## A toolkit you can read in one sitting

Everything you import lives at the top level of the `idunn` package:

```python
from idunn import Port, Adapter, Invert     # the three decorators — the entire authoring surface
from idunn import Idunn                      # the one container; you touch it once, to discover
from idunn import LifecycleEnum              # TRANSIENT (default) or SINGLETON, passed to @Adapter
from idunn import IdunnError                 # the base of the exception hierarchy you catch
```

That is the surface area on purpose. There is no registry object to thread through your code, no
service locator to import, and — deliberately — **no public `resolve()`**. The only way to start
an object graph is to construct an `@Invert`-decorated object; from there the graph wires itself.
A toolkit small enough to read on a coffee break is small enough to trust.

## The Idunn model

Three roles, in a straight line: **Port → Adapter → `@Invert` consumer.** A contract, an
implementation of that contract, and a consumer that receives the implementation without ever
naming it.

### Ports define contracts

A port is a `typing.Protocol` marked with `@Port`. It names a capability and says nothing about
how that capability is met. Marking a non-`Protocol` raises `InvalidPortError`; the decorated
protocol is made `runtime_checkable` so an adapter can be verified against it.

```python
from typing import Protocol
from idunn import Port


@Port
class LoggerPort(Protocol):
    def write(self, line: str) -> None: ...
```

### Adapters wear a badge

An adapter is a concrete class marked with `@Adapter(port, ...)`. The decorator attaches
metadata and **constructs nothing** — it is a label, not a factory. An adapter has to actually
satisfy its port (structurally or by inheritance); Idunn never synthesizes or mutates the class
to make it fit.

```python
from idunn import Adapter, LifecycleEnum


@Adapter(LoggerPort, lifecycle=LifecycleEnum.SINGLETON)
class FileLogger(LoggerPort):
    def write(self, line: str) -> None:
        print(f"[file] {line}")   # imagine an append to disk
```

"Wearing the badge" is a hard rule. A class that *looks* exactly like an adapter but lacks the
`@Adapter` decorator is invisible to Idunn — looking the part is not the same as wearing the
badge. That explicitness is what keeps registration honest.

### `@Invert` receives dependencies

A consumer marks its `__init__` with `@Invert`. Every constructor parameter whose type hint is a
`@Port` is resolved from the process-wide `Idunn()` container *when the constructor runs* and
assigned to `self.<name>`. The resolved value is also forwarded into the constructor body, so the
body can use it normally.

```python
from idunn import Invert


class Service:
    logger: LoggerPort                       # declared for the type checker; @Invert assigns it

    @Invert
    def __init__(self, logger: LoggerPort, name: str) -> None:
        self.name = name                     # self.logger is injected and assigned for you

    def run(self) -> None:
        self.logger.write(f"{self.name} started")
```

Three properties make this pleasant to live with:

- **A caller-supplied argument always wins.** `Service(logger=fake_logger, name="t")` skips
  injection for `logger`, so the class stays trivially testable — hand it a notebook instead of
  the real logger and nothing else changes.
- **Resolution is recursive.** If the chosen adapter's own constructor takes `@Port` parameters,
  those resolve first, all the way down.
- **You never call the container.** No `resolve`, no locator, no wiring code in business logic.

## A worked example

The pieces above are the entire toolkit. Here is how they compose, from the simplest case to the
ones that earn a little more ceremony. Assume the ports and adapters live under a `telemetry`
package, discovered once at startup:

```python
from idunn import Idunn

report = Idunn().autodiscover("telemetry")   # imports & registers every @Port/@Adapter under it
```

`autodiscover` is the single registration step. It imports only modules whose dotted names
contain `port`, `ports`, `adapter`, or `adapters`, registers ports before adapters, and ignores
undecorated classes. It returns a `ReportMap` — a small record of what was imported and
registered — handy for a startup log or a sanity assertion in a test.

### One adapter, zero decisions

Most ports have exactly one implementation and the caller does not care which. Register it
unkeyed and Idunn just hands it over — the implementation stays hidden behind the port, which is
the entire point of a port.

```python
@Adapter(LoggerPort)
class FileLogger(LoggerPort):
    def write(self, line: str) -> None: ...


class Service:
    logger: LoggerPort                       # assigned by @Invert

    @Invert
    def __init__(self, logger: LoggerPort) -> None:
        pass


Idunn().autodiscover("telemetry")
Service().logger.write("hello")              # the one unkeyed adapter is resolved and injected
```

Exactly one *unkeyed* adapter may be active per port in any environment — so an unkeyed resolve
always has exactly one answer. This is the case you want most of the time.

### Two adapters, one environment

When several implementations are all valid at the same time and the environment can't tell them
apart, give each a **key**. The cleanest place to choose is the point of use, with
`@Invert(keys={...})` — the decision sits right next to the code that depends on it.

```python
@Adapter(LoggerPort, key="file")
class FileLogger(LoggerPort):
    def write(self, line: str) -> None: ...


@Adapter(LoggerPort, key="cloud")
class CloudLogger(LoggerPort):
    def write(self, line: str) -> None: ...


class Auditor:
    logger: LoggerPort                       # assigned by @Invert

    @Invert(keys={"logger": "cloud"})
    def __init__(self, logger: LoggerPort) -> None:
        pass
```

The one rule, worth repeating: **a keyed adapter never answers an unkeyed resolve.** If `file`
and `cloud` are your *only* adapters for `LoggerPort`, a plain `@Invert` parameter typed
`LoggerPort` raises `AdapterNotFoundError` — there is no unkeyed apple in the basket. Pick one
with `keys={...}`, or register an unkeyed adapter as the default.

### The same role across environments

When the *same role* needs *different apples* in dev, test, and production, put the environment
in the decorator instead of reaching for keys. No YAML, no 200-line `settings.py`.

```python
@Adapter(LoggerPort, envs={"prod"})
class CloudLogger(LoggerPort):
    def write(self, line: str) -> None: ...


@Adapter(LoggerPort, envs={"test", "ci"})
class MemoryLogger(LoggerPort):
    def write(self, line: str) -> None: ...
```

`envs=None` (the default) means active everywhere — the apple for all seasons. The active
environment comes from `IDUNN_ENV`, defaulting to `local`, normalized to lowercase with
underscores turned to hyphens (so `My_Env` and `my-env` are the same place). Because the two
adapters above are never active at once, an unkeyed resolve still has exactly one answer and the
consumer code never changes between environments.

Idunn guards this invariant. Register two adapters that share a port and key (unkeyed counts as
"no key") and are both active in an overlapping environment, and it raises `InvalidAdapterError`
rather than silently guessing which apple you meant — two apples, one label, same shelf.

### Optional dependencies

A port parameter typed `LoggerPort | None`, or any `@Port` parameter with a default, is
**optional**: if no adapter is active, the default — or `None` — is used instead of raising. The
rule is identical inside an adapter's own constructor, not just at the consumer boundary.

```python
class Service:
    @Invert
    def __init__(self, logger: LoggerPort | None = None) -> None:
        self.logger = logger                 # None if nothing satisfies LoggerPort
```

Optionality is expressed in the type hint, where it belongs — not in a configuration flag
somewhere else.

## The features Idunn refuses

Half of Idunn's design is the features it cheerfully declines to grow:

- No external YAML configuration.
- No package-wide global scanning, no subclass scanning.
- No "the class name ends with `Adapter`, so register it" guesswork.
- No implicit protocol matching for registration — the badge is required.
- No construction during decoration, and none during autodiscovery.
- No field injection, no setter injection.
- No loose global resolver functions, and no public `resolve()`.

Each "no" removes a way for wiring to become implicit, surprising, or hard to trace. Injection
happens at exactly one moment — when an `@Invert` constructor runs — and registration happens for
exactly one reason — a decorator was applied and discovered. That short list *is* the feature: as
simple as possible, and not one apple simpler.

## One container per process

`Idunn()` is a single process-wide container; call it a thousand times and you get back the same
barrel of apples. That choice buys simplicity at a few honest prices:

- **One container per process.** There is no second, independent container — everything shares
  the same `Idunn()`. Multi-container setups are out of scope.
- **Not thread-safe.** Wire everything at startup on one thread, *then* resolve. Registration and
  resolution mutate shared state without locking.
- **Test isolation is your job.** Clear state between tests with `Idunn().reset()` (often an
  autouse fixture); `Idunn().reset(environment="prod")` also rebinds the active environment for a
  test. And when you want to *see* the wired graph, `Idunn().describe()` returns a readable
  snapshot of the active port → adapter bindings.

These are deliberate trade-offs, not oversights. A startup-time, single-process container is the
simplest thing that serves the toolkit's goal, and Idunn refuses to pretend otherwise.

## Where to go next

- **[README](../README.md)** — the full reference: decorator signatures, the complete
  adapter-selection rules, lifecycles, and the exception table.
- **[`ADVANCED.md`](./ADVANCED.md)** — how resolution fires, inspecting the graph with
  `describe()`, manual registration, test isolation, and the deliberate non-features.
- **[`classes.md`](./classes.md)** — a class-by-class catalog of the package.

The everyday API never grows past the three decorators and `autodiscover`. Everything else is a
door you can open when you need it — and most days, you won't.
