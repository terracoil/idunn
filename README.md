# Idunn

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-landscape-2560x900.png)

**Idunn** is a tiny, opinionated **constructor-time** dependency-inversion toolkit for Python:
dependencies arrive when an `@Invert()` constructor or function is called, and not a moment sooner.
Three decorators, one discovery call, nothing to configure.

> *"Everything should be made as simple as possible, but not simpler."* — Albert Einstein

The name comes from **Iðunn**, the Norse keeper of the apples that keep the gods young. A port is an
empty basket, an adapter is the apple you put in it, and a consumer just asks for the basket. Nobody
has to know which orchard it came from, which is rather the point of dependency inversion.

This file is the everyday reference. **[About Idunn](./docs/ABOUT.md)** explains why it looks the
way it does, and **[Advanced](./docs/ADVANCED.md)** covers environments, keys, testing with
`idunn.testing` and the engine, for the days the everyday is not enough.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Introduction

### Installation

```bash
pip install idunn        # or: poetry add idunn
```

`idunn` (lowercase) is the package; `Idunn` (the class) is the one process-wide container inside it.
`Idunn()` always returns that same shared instance, so there is nothing to pass around and nothing
to misplace.

### Importing

```python
from idunn import Port, Adapter, Invert  # the three decorators
from idunn import Idunn  # the container: autodiscover() once, or bootstrap() per entry point
from idunn import LifecycleEnum  # TRANSIENT (default) or SINGLETON, passed to @Adapter
from idunn import IdunnError  # base of the exception family
from idunn import ReportMap  # the TypedDict autodiscover() and bootstrap() return
```

That, plus the six `IdunnError` subclasses, is everything an application imports; its tests
borrow one more name, `Harness`, from `idunn.testing`. Registration, selection and construction
happen behind the container, where business code cannot get attached to them.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Discovery: `autodiscover` and `bootstrap`

Idunn registers nothing on import. Decorators only attach metadata, and one discovery call imports
your modules so the decorated classes get catalogued. Both calls import every module under
`root_package` (skipping `__main__.py`, test modules and anything you `exclude`) and register each
class wearing `@Port` or `@Adapter`, whatever its module is called. The package you name is the
boundary: nothing outside it is scanned or registered. Your modules may still import what they
like; Idunn just won't catalogue it. Ports register before adapters, undecorated classes are
ignored, and nothing is constructed.

Since discovery imports everything under the root, module import should be cheap and free of side
effects. Put scripts behind `if __name__ == '__main__':`, and `exclude=` the modules that do work
at import or need optional dependencies you have not installed.

| Call | Use it when | Behavior |
|---|---|---|
| `Idunn().autodiscover('my_app')` | You own the process: an application with a `main()`, an app factory, or a startup hook. | Discovers every time it is called. Call it once at startup, before the first `@Invert()` object is built. |
| `Idunn().bootstrap('my_lib')` | You ship a library and have no startup hook to call `autodiscover` from. | `autodiscover`, guarded to run once per root. Call it from every public entry point: the first call discovers, later calls return the cached report. Thread-safe, even when called while a module is being imported. |

### Applications

An application owns its process, so it discovers once at startup and then builds the object graph:

```python
# your_app/ports.py
from typing import Protocol

from idunn import Port


@Port
class GreeterPort(Protocol):
  def greet(self, name: str) -> str: ...
```

```python
# your_app/adapters.py
from idunn import Adapter

from .ports import GreeterPort


@Adapter(GreeterPort)
class PlainGreeterAdapter:
  def greet(self, name: str) -> str:
    return f'Hello, {name}'
```

```python
# your_app/main.py
from idunn import Idunn, Invert

from .ports import GreeterPort


class App:
  greeter: GreeterPort  # assigned by @Invert

  @Invert()
  def __init__(self, *, greeter: GreeterPort) -> None:
    pass

  def run(self) -> None:
    print(self.greeter.greet('Idunn'))  # Hello, Idunn


if __name__ == '__main__':
  Idunn().autodiscover('your_app')  # once, at startup
  App().run()  # App.__init__ is @Invert()-decorated; the graph wires itself
```

### Libraries

A library is imported, not started, and discovery at import time is a side effect nobody ordered.
Put `bootstrap` inside the library's own entry points so wiring happens the first time anyone uses
it, and bootstrap the narrowest package that holds your ports and adapters:

```python
# my_lib/ports.py
from typing import Protocol

from idunn import Port


@Port
class StoragePort(Protocol):
  def save(self, key: str, value: str) -> None: ...
```

```python
# my_lib/adapters.py
from idunn import Adapter, LifecycleEnum

from .ports import StoragePort


@Adapter(StoragePort, lifecycle=LifecycleEnum.SINGLETON)
class MemoryStorageAdapter:
  def __init__(self) -> None:
    self.items: dict[str, str] = {}

  def save(self, key: str, value: str) -> None:
    self.items[key] = value
```

```python
# my_lib/api.py
from idunn import Idunn, Invert

from .ports import StoragePort


class Engine:
  storage: StoragePort  # assigned by @Invert

  @Invert()
  def __init__(self, *, storage: StoragePort) -> None:
    pass

  def store(self, key: str, value: str) -> None:
    self.storage.save(key, value)


class MyLib:
  """Public entry point; wires my_lib on first use."""

  def __init__(self) -> None:
    Idunn().bootstrap('my_lib')  # discovers once; a dict lookup afterwards
    self._engine = Engine()  # @Invert() supplies the storage

  def remember(self, key: str, value: str) -> None:
    self._engine.store(key, value)
```

Both calls return a `ReportMap` listing the modules imported and the classes registered, which
makes a tidy startup log line. `autodiscover` lists only what *that call* registered (a repeat run
lists none); `bootstrap` returns the root's cached report, which covers everything its first
discovery registered. Discovery accumulates, so an application can `autodiscover` its own package
while every library it uses quietly bootstraps itself.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Normal usage

Discovery finds every `@Port` and `@Adapter` under the root you name, whatever the modules are
called. For a small app the layout below is all you need: a `ports.py`, an `adapters.py`, and your
entry point beside them. As it grows, turn either file into a package (`ports/`,
`adapters/stripe.py`) or give each feature its own pair (`billing/ports.py`, `billing/adapters.py`).
The names are for the people reading your code; Idunn doesn't check them. Decorate the consumer's
constructor with `@Invert()`, discover once, then construct.

```text
my_app/
  __init__.py
  main.py
  ports.py
  adapters.py
```

The same app lives in [`examples/classy/simple`](./examples/classy/simple/).

```python
# my_app/ports.py
from typing import Protocol

from idunn import Port


@Port
class AppleBasketPort(Protocol):
  """Source of apples that keep the gods young."""

  def take_apple(self) -> str:
    """Return an apple from the basket."""
    ...
```

```python
# my_app/adapters.py
from idunn import Adapter, LifecycleEnum

from .ports import AppleBasketPort


@Adapter(AppleBasketPort, lifecycle=LifecycleEnum.SINGLETON)
class GoldenAppleBasketAdapter(AppleBasketPort):
  """The one basket ``AppleBasketPort`` resolves to, built once and shared by everyone."""

  def take_apple(self) -> str:
    """Hand out a golden apple."""
    return 'youth restored'
```

```python
# my_app/main.py
from idunn import Idunn, Invert

from .ports import AppleBasketPort


class Feast:
  """An ``@Invert()`` root: its basket arrives when it is constructed.
  The port sits after ``*``, keyword-only, so ``Feast('Bragi')`` can only mean the host.
  """

  basket: AppleBasketPort  # declared for the type checker; @Invert assigns it

  @Invert()
  def __init__(self, host: str, *, basket: AppleBasketPort) -> None:
    """Keep ``host``; ``self.basket`` is already injected and assigned by the time this runs."""
    self.host: str = host

  def serve(self) -> str:
    """Serve the feast with an apple from the injected basket."""
    return f'{self.host}: {self.basket.take_apple()}'


if __name__ == '__main__':
  Idunn().autodiscover('my_app')
  print(Feast('Bragi').serve())  # Bragi: youth restored
```

Run it as a module, `python -m my_app.main`. Run by path, the relative imports have nothing to be
relative to and Python says so. In this repo the copy sits two packages deeper, so it runs with
`poetry run python -m examples.classy.simple.main` and discovers `'examples.classy.simple'`. That
root is the one line that differs from the listings above; the files also keep module docstrings,
which the listings leave out to spare you the scrolling.

More examples: [`examples/functional/simple`](./examples/functional/simple/) is the same app
with an `@Invert()` function where the class was, and
[`examples/classy/complex`](./examples/classy/complex/) and
[`examples/functional/complex`](./examples/functional/complex/) run a small shop that leans on most
of [Advanced](./docs/ADVANCED.md), once with classes and once with functions. The suite runs all
four and checks every line they print.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## The three decorators

* ### `@Port`
  Marks a `typing.Protocol` as a contract. Anything that is not a Protocol raises
  `InvalidPortError`. The Protocol is made `runtime_checkable` so Idunn can confirm each adapter
  actually satisfies it, instead of taking its word for it.

* ### `@Adapter(port, lifecycle=...)`
  Declares a concrete class as the implementation of `port`. It attaches metadata and constructs
  nothing. The class must satisfy the Protocol itself, by inheritance or structurally; inheritance
  is recommended because then your type checker, and your colleagues, can see the relationship.
  Idunn never patches a class to fit. One adapter per port is the normal case. `lifecycle` is
  `TRANSIENT` by default (a new instance per resolve) or `SINGLETON` (built once, shared).
  <br/><br/>Choosing between several adapters with `key=` and `envs=` is covered in
  [Advanced](./docs/ADVANCED.md#choosing-between-adapters).

* ### `@Invert()`
  Wraps a consumer's `__init__`. Every parameter whose type hint is a `@Port` is resolved when the
  constructor runs, assigned to `self.<name>`, and passed into the body. On any other function it
  does the same at call time, minus the assignment: the ports arrive as keyword arguments and
  nothing is kept anywhere.

  ```python
  @Invert()
  def harvest(orchard: str, *, basket: AppleBasketPort) -> str:
    return f'{orchard}: {basket.take_apple()}'


  harvest('Asgard')  # basket is resolved and passed in; harvest(..., basket=fake) skips that
  ```

  Four things to know:
  - A caller-supplied argument always wins, so `Feast('x', basket=fake)` skips injection and the
    class stays easy to test.
  - Port parameters are keyword-only: declare them after `*`, and `@Invert()` refuses anything
    else. So `Feast('Bragi')` can only mean `host`, and a port you supply yourself goes by name.
  - Resolution is recursive: an adapter's own `@Port` constructor parameters are resolved first.
  - Calling an `@Invert()` constructor or function is the only way to start a graph. There is no
    `resolve()`. Always apply it with parentheses. Keyed selection, explicit parameter maps and
    optional dependencies are in [Advanced](./docs/ADVANCED.md#the-invert-contract-in-full).

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## What gets registered

Only classes wearing the decorator, defined at module level in a module under the root. A class that
satisfies a port but lacks `@Adapter(...)` is invisible to discovery. So is an undecorated subclass
of an adapter, a decorated class in a test module or an `exclude`d one, and a decorated class
imported from another package (discover that package as its own root). Looking the part is not the
same as wearing the badge, and Idunn would rather be told than guess.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Development

```bash
poetry install --with dev
poetry run pytest
poetry run ruff format --check . && poetry run ruff check .
poetry run mypy
```

CI (`.github/workflows/ci.yml`) runs the lock, format, lint and type checks once and the tests on
Python 3.11, 3.12, 3.13.16 and 3.14. `poetry.lock` is committed, so run `poetry lock` after touching
dependencies, or CI will notice. Idunn supports Python 3.11 and newer
(`requires-python = ">=3.11,<4.0"`) and is developed on 3.13.16.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Going further

- [About Idunn](./docs/ABOUT.md): the model, and the reasons behind the short list of things it
  refuses to do.
- [Advanced](./docs/ADVANCED.md): environments and keys, the full `@Invert` contract, discovery
  options, `describe()`, testing with `idunn.testing`, exceptions, limitations, and maintainer
  notes.
- [Class catalog](./docs/classes.md): every class in the package, public or hidden.
- [Changelog](./CHANGELOG.md): what changed in each release, and what to fix when upgrading to 2.0.
