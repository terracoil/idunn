# About Idunn

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-landscape-2560x900.png)

> This is the story of Idunn: the idea, the model, and the design choices behind it. For the
> everyday reference read the [README](../README.md); for everything beyond normal usage see
> [`ADVANCED.md`](./ADVANCED.md).

*"Everything should be made as simple as possible, but not simpler."* — Albert Einstein

Idunn is a tiny dependency-inversion toolkit for Python. You can learn the whole of it from three
decorators and one discovery call, and the rest of this article explains why it stops there, and why
that restraint is the point.

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

The name comes from **Iðunn**, the Norse keeper of the apples that kept the gods young. It is a
fitting image for dependency inversion: keep the right dependencies close to the system and the code
stays fresh, instead of hardening into the brittle, hand-wired tangle that makes future-you sigh. A
port is an empty basket; an adapter is the apple you put in it; a consumer simply asks for the basket
and trusts that the right apple is inside.

The metaphor is not decoration. Once you think in baskets and apples, the entire API follows.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## A toolkit you can read in one sitting

Everything you import lives at the top level of the `idunn` package:

```python
from idunn import Port, Adapter, Invert  # the three decorators: the entire authoring surface
from idunn import Idunn  # the one container; you touch it once, to discover
from idunn import LifecycleEnum  # TRANSIENT (default) or SINGLETON, passed to @Adapter
from idunn import IdunnError  # the base of the exception hierarchy you catch
from idunn import ReportMap  # the TypedDict autodiscover() and bootstrap() return
```

That is the surface area on purpose. There is no registry object to thread through your code, no
service locator to import, and, deliberately, **no public `resolve()`**. The only way to start an
object graph is to construct an `@Invert()`-decorated object; from there the graph wires itself. A
toolkit small enough to read on a coffee break is small enough to trust.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## The Idunn model

Three roles in a straight line: **Port, Adapter, `@Invert` consumer.** A contract, an implementation
of that contract, and a consumer that receives the implementation without ever naming it.

### Ports define contracts

A port is a `typing.Protocol` marked with `@Port`. It names a capability and says nothing about how
that capability is met. Marking a non-Protocol raises `InvalidPortError`; the decorated Protocol is
made `runtime_checkable` so an adapter can be verified against it.

```python
from typing import Protocol

from idunn import Port


@Port
class LoggerPort(Protocol):
  def write(self, line: str) -> None: ...
```

### Adapters wear a badge

An adapter is a concrete class marked with `@Adapter(port, ...)`. The decorator attaches metadata and
**constructs nothing**: it is a label, not a factory. The class has to satisfy its port, structurally
or by inheritance; Idunn never synthesizes or mutates it to fit.

```python
from idunn import Adapter, LifecycleEnum


@Adapter(LoggerPort, lifecycle=LifecycleEnum.SINGLETON)
class FileLogger(LoggerPort):
  def write(self, line: str) -> None:
    print(f'[file] {line}')  # imagine an append to disk
```

Wearing the badge is a hard rule. A class that looks exactly like an adapter but lacks `@Adapter` is
invisible to Idunn. That explicitness is what keeps registration honest.

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
  injection for `logger`, so the class stays trivially testable.
- **Resolution is recursive.** If the chosen adapter's own constructor takes `@Port` parameters,
  those resolve first, all the way down.
- **You never call the container.** No `resolve`, no locator, no wiring code in business logic.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## A worked example

The pieces above are the entire toolkit. Here is how they compose, from the simplest case to the ones
that earn a little more ceremony. Assume the ports and adapters live under a `telemetry` package,
discovered once at startup:

```python
from idunn import Idunn

report = Idunn().autodiscover('telemetry')  # imports and registers every @Port/@Adapter under it
```

That is the single registration step for an application. A library, which has no startup to speak
of, calls `Idunn().bootstrap('telemetry')` from its entry points instead and gets the same result on
first use. Either way the call returns a `ReportMap` of what was imported and registered, handy for a
startup log.

### One adapter, zero decisions

Most ports have exactly one implementation and the caller does not care which. Register it unkeyed
and Idunn hands it over; the implementation stays hidden behind the port, which is the entire point of
a port.

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

Exactly one unkeyed adapter may be active per port in any environment, so an unkeyed resolve always
has exactly one answer. This is the case you want most of the time.

### Two adapters, one environment

When several implementations are valid at the same time, give each a **key** and choose at the point
of use with `@Invert(keys={...})`. The decision sits right next to the code that depends on it.

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
`AdapterNotFoundError`. Pick one with `keys=`, or register an unkeyed adapter as the default.

### The same role across environments

When the same role needs different apples in dev, test, and production, put the environment in the
decorator instead of reaching for keys. No YAML, no 200-line `settings.py`.

```python
@Adapter(LoggerPort, envs={'prod'})
class CloudLogger(LoggerPort): ...


@Adapter(LoggerPort, envs={'test', 'ci'})
class MemoryLogger(LoggerPort): ...
```

`envs=None`, the default, means active everywhere. The active environment comes from `IDUNN_ENV`
and defaults to `local`. Because the two adapters above are never active at once, an unkeyed resolve
still has exactly one answer and the consumer never changes between environments. Register two
adapters that share a port and key and overlap in an environment, and Idunn raises
`InvalidAdapterError` rather than guessing which apple you meant.

### Optional dependencies

A parameter typed `LoggerPort | None`, or any `@Port` parameter with a default, is **optional**: if
no adapter is active, the default, or `None`, is used instead of raising. The rule is identical inside
an adapter's own constructor.

```python
class Service:
  @Invert()
  def __init__(self, logger: LoggerPort | None = None) -> None:
    self.logger = logger  # None if nothing satisfies LoggerPort
```

Optionality is expressed in the type hint, where it belongs, not in a configuration flag somewhere
else.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## The features Idunn refuses

Half of Idunn's design is the features it cheerfully declines to grow: no YAML, no package-wide or
subclass scanning, no name-based guessing, no implicit protocol matching, no construction during
decoration or discovery, no field or setter injection, and no public `resolve()`. The full list,
with the reasoning for each, is in [`ADVANCED.md`](./ADVANCED.md#limitations-and-non-features).

Each "no" removes a way for wiring to become implicit, surprising, or hard to trace. Injection
happens at exactly one moment, when an `@Invert()` constructor runs, and registration happens for
exactly one reason, a decorator was applied and discovered. That short list *is* the feature: as
simple as possible, and not one apple simpler.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## One container per process

`Idunn()` is a single process-wide container; call it a thousand times and you get back the same
barrel of apples. That choice buys simplicity at a few honest prices: there is no second container,
registration and resolution are not thread-safe, and test isolation is your job via `Idunn().reset()`.
When you want to see the wired graph, `Idunn().describe()` returns a readable snapshot of the active
bindings.

These are deliberate trade-offs, not oversights. A startup-time, single-process container is the
simplest thing that serves the toolkit's goal, and Idunn refuses to pretend otherwise.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Where to go next

- **[README](../README.md)**: install, discovery, and the normal-usage example.
- **[`ADVANCED.md`](./ADVANCED.md)**: environments and keys, the full `@Invert` contract,
  discovery options, `describe()`, test isolation, exceptions, and the non-features.
- **[`classes.md`](./classes.md)**: a class-by-class catalog of the package.

The everyday API never grows past the three decorators and one discovery call. Everything else is a
door you can open when you need it, and most days you won't.
