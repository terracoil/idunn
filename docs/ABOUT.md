# About Idunn

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-landscape-2560x900.png)

> This is the story of Idunn: the idea, the model, and the design choices behind it. For the
> everyday reference read the [README](../README.md); for everything beyond normal usage see
> [`ADVANCED.md`](./ADVANCED.md).

*"Everything should be made as simple as possible, but not simpler."* — Albert Einstein

Idunn is a tiny dependency-inversion toolkit for Python. You can learn all of it from three
decorators and one discovery call. The rest of this article explains why it stops there, and why
stopping there is the feature rather than an oversight.

## Contents

- [The apples and the metaphor](#the-apples-and-the-metaphor)
- [A toolkit you can read in one sitting](#a-toolkit-you-can-read-in-one-sitting)
- [The Idunn model](#the-idunn-model)
- [A worked example](#a-worked-example)
- [The features Idunn refuses](#the-features-idunn-refuses)
- [One container per process](#one-container-per-process)
- [Where to go next](#where-to-go-next)

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## The apples and the metaphor

The name comes from **Iðunn**, the Norse keeper of the apples that kept the gods young. It suits
dependency inversion: keep the right dependencies close and swappable and the code stays fresh,
instead of hardening into the hand-wired tangle that makes future-you sigh. A port is an empty
basket; an adapter is the apple you put in it; a consumer asks for the basket and trusts that the
right apple is inside.

The metaphor is load-bearing. Once you think in baskets and apples, the API mostly writes itself.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## A toolkit you can read in one sitting

Everything you import lives at the top level of the `idunn` package:

```python
from idunn import Port, Adapter, Invert  # the three decorators: the entire authoring surface
from idunn import Idunn  # the one container; you touch it only to discover
from idunn import LifecycleEnum  # TRANSIENT (default) or SINGLETON, passed to @Adapter
from idunn import IdunnError  # the base of the exception family you catch
from idunn import ReportMap  # the TypedDict autodiscover() and bootstrap() return
```

The surface is small on purpose. There is no registry object to thread through your code, no
service locator to import, and, deliberately, **no public `resolve()`**. The only way to start an
object graph is to construct an `@Invert()`-decorated object; from there the graph wires itself. A
container you can call from anywhere ends up called from everywhere, and then your business logic
knows about your wiring. A toolkit small enough to read on a coffee break is also small enough to
trust.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## The Idunn model

Three roles in a straight line: **Port, Adapter, `@Invert` consumer.** A contract, an implementation
of that contract, and a consumer that receives the implementation without ever naming it.

### Ports define contracts

A port is a `typing.Protocol` marked with `@Port`. It names a capability and says nothing about how
that capability is met. Marking a non-Protocol raises `InvalidPortError`. The decorated Protocol is
made `runtime_checkable`, so every adapter is checked against it when it is built rather than
trusted on sight.

```python
from typing import Protocol

from idunn import Port


@Port
class LoggerPort(Protocol):
  def write(self, line: str) -> None: ...
```

### Adapters wear a badge

An adapter is a concrete class marked with `@Adapter(port, ...)`. The decorator attaches metadata
and **constructs nothing**: it is a label, not a factory. The class has to satisfy its port,
structurally or by inheritance; Idunn never synthesizes or mutates it to fit.

```python
from idunn import Adapter, LifecycleEnum


@Adapter(LoggerPort, lifecycle=LifecycleEnum.SINGLETON)
class FileLogger(LoggerPort):
  def write(self, line: str) -> None:
    print(f'[file] {line}')  # imagine an append to disk
```

Wearing the badge is a hard rule. A class that looks exactly like an adapter but lacks `@Adapter` is
invisible to Idunn. That is what keeps registration honest: every binding in the graph can be found
by searching for one decorator, and nothing joins the party because its name happened to fit.

### `@Invert` receives dependencies

A consumer marks its `__init__` with `@Invert()`. Every constructor parameter whose type hint is a
`@Port` is resolved from the process-wide `Idunn()` container when the constructor runs, assigned to
`self.<name>`, and forwarded into the body.

```python
from idunn import Invert


class Service:
  logger: LoggerPort  # declared for the type checker; @Invert assigns it

  @Invert()
  def __init__(self, logger: LoggerPort, name: str) -> None:
    self.name = name  # self.logger is injected and assigned for you

  def run(self) -> None:
    self.logger.write(f'{self.name} started')
```

Three properties make this pleasant to live with:

- **A caller-supplied argument always wins.** `Service(logger=fake_logger, name='t')` skips
  injection for `logger`, so the class stays trivially testable without any container at all.
- **Resolution is recursive.** If the chosen adapter's own constructor takes `@Port` parameters,
  those resolve first, all the way down.
- **You never call the container.** No `resolve`, no locator, no wiring code in business logic.

The one courtesy asked in return: pass plain arguments by keyword. A positional argument fills the
next parameter in line, and `@Invert` is not going to argue with you about whether it was a port.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## A worked example

The pieces above are the whole toolkit. Here is how they compose, from the simplest case to the ones
that earn a little more ceremony. Assume the ports and adapters live under a `telemetry` package,
discovered once at startup:

```python
from idunn import Idunn

report = Idunn().autodiscover('telemetry')  # imports and registers every @Port/@Adapter under it
```

That is the single registration step for an application. The module names inside `telemetry` are
yours to choose; the decorator is what counts. A library, which has no startup to speak of, calls
`Idunn().bootstrap('telemetry')` from its entry points instead and gets the same result on first
use. Either way the call returns a `ReportMap` of what was imported and newly registered, handy for
a startup log.

### One adapter, zero decisions

Most ports have exactly one implementation and the caller does not care which. Register it unkeyed
and Idunn hands it over; the implementation stays hidden behind the port, which is the entire point
of having a port.

```python
@Adapter(LoggerPort)
class FileLogger(LoggerPort):
  def write(self, line: str) -> None: ...


class Service:
  logger: LoggerPort  # assigned by @Invert

  @Invert()
  def __init__(self, logger: LoggerPort) -> None:
    pass


Idunn().autodiscover('telemetry')
Service().logger.write('hello')  # the one unkeyed adapter is resolved and injected
```

At most one unkeyed adapter may be active per port in any environment, so an unkeyed resolve never
has to choose. This is the case you want most of the time.

### Two adapters, one environment

When several implementations are valid at the same time, give each a **key** and choose at the point
of use with `@Invert(keys={...})`. The decision sits next to the code that depends on it, not in a
configuration file three directories away.

```python
@Adapter(LoggerPort, key='file')
class FileLogger(LoggerPort): ...


@Adapter(LoggerPort, key='cloud')
class CloudLogger(LoggerPort): ...


class Auditor:
  logger: LoggerPort  # assigned by @Invert

  @Invert(keys={'logger': 'cloud'})
  def __init__(self, logger: LoggerPort) -> None:
    pass
```

The one rule worth repeating: **a keyed adapter never answers an unkeyed resolve.** If `file` and
`cloud` are the only adapters for `LoggerPort`, a plain `@Invert()` parameter raises
`AdapterNotFoundError`. Pick one with `keys=`, or register an unkeyed adapter as the default. Keys
are opt-in so that adding a specialist never changes what everyone else gets.

### The same role across environments

When the same role needs different apples in dev, test and production, put the environment in the
decorator instead of reaching for keys. No YAML, no 200-line `settings.py`.

```python
@Adapter(LoggerPort, envs={'prod'})
class CloudLogger(LoggerPort): ...


@Adapter(LoggerPort, envs={'test', 'ci'})
class MemoryLogger(LoggerPort): ...
```

`envs=None`, the default, means active everywhere. The active environment comes from
`Idunn().reset(environment=...)`, then `IDUNN_ENV`, then `local`, and it is read once, when the
container is created or reset. Because the two adapters above are never active at once, an unkeyed
resolve still has one answer and the consumer never changes between environments. Register two
adapters that share a port and key and overlap in an environment, and Idunn raises
`InvalidAdapterError` rather than guessing which apple you meant.

### Optional dependencies

A parameter typed `LoggerPort | None`, or any `@Port` parameter with a default, is **optional**: if
no adapter is active, the default, or `None`, is used instead of raising. The rule is identical
inside an adapter's own constructor.

```python
class Service:
  @Invert()
  def __init__(self, logger: LoggerPort | None = None) -> None:
    self.logger = logger  # None if nothing satisfies LoggerPort
```

Optionality lives in the type hint, where readers and type checkers already look, not in a flag
somewhere else that both of them will miss.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## The features Idunn refuses

Half of Idunn's design is the features it politely declines to grow: no YAML, no scanning outside
the root, no subclass scanning, no name-based guessing, no implicit protocol matching, no
construction during decoration or discovery, no field or setter injection, and no public
`resolve()`. The full list, with the reasoning for each, is in
[`ADVANCED.md`](./ADVANCED.md#limitations-and-non-features).

Each "no" removes a way for wiring to become implicit, surprising or hard to trace. Injection
happens at exactly one moment, when an `@Invert()` constructor runs, and registration happens for
exactly one reason, a decorator was applied and discovered. When something is wired wrong, there
are two places to look, not twenty. That short list *is* the feature: as simple as possible, and
not one apple simpler.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## One container per process

`Idunn()` is a single process-wide container; call it a thousand times and you get back the same
barrel of apples. That choice buys simplicity at a few honest prices: there is no second container,
resolution is not thread-safe, and test isolation is your job via `Idunn().reset()`. When you want
to see the wired graph, `Idunn().describe()` returns a readable snapshot of the active bindings.

These are deliberate trade-offs, not oversights. Wiring is meant to happen once, at startup, on one
thread, and a container built for that needs no locks around resolution, no scopes and no second
instance. Idunn declines to pretend otherwise. Registration takes a lock all the same: the catalog
is copy-on-write, so the lock costs readers nothing and nobody ever sees half a registration.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Where to go next

- **[README](../README.md)**: install, discovery, and the normal-usage example.
- **[`ADVANCED.md`](./ADVANCED.md)**: environments and keys, the full `@Invert` contract,
  discovery options, `describe()`, test isolation, exceptions, and the non-features.
- **[`classes.md`](./classes.md)**: a class-by-class catalog of the package.

The everyday API never grows past the three decorators and one discovery call. Everything else is a
door you can open when you need it, and most days you won't.
