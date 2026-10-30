# Idunn

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-landscape-2560x900.png)

**Idunn** is a tiny Python dependency-inversion toolkit built around **constructor-time injection
only**: three decorators, one discovery call, nothing to configure.

> *"Everything should be made as simple as possible, but not simpler."* — Albert Einstein

The name comes from **Iðunn**, the Norse keeper of the apples that keep the gods young. A port is an
empty basket, an adapter is the apple you put in it, and a consumer just asks for the basket.

This file is the everyday reference. Read **[About Idunn](./docs/ABOUT.md)** for the thinking behind
it and **[Advanced](./docs/ADVANCED.md)** for environments, keys, test isolation, and the engine.

---
![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Introduction
### Installation
```bash
pip install idunn        # or: poetry add idunn
```

`idunn` (lowercase) is the package; `Idunn` (the class) is the one process-wide container inside it.
`Idunn()` always returns that same shared instance.


### Importing

```python
from idunn import Port, Adapter, Invert  # the three decorators
from idunn import Idunn  # the container: autodiscover() or bootstrap(), once
from idunn import LifecycleEnum  # TRANSIENT (default) or SINGLETON, passed to @Adapter
from idunn import IdunnError  # base of the exception hierarchy
```

That is the entire surface. Registration, selection, and construction happen behind the container.

---


<div class="image-container">
  <img src="https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png" alt="Idunn" class="center-img">
</div>

[//]: # (<img src="https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png" alt="Idunn" class="center-img">)

## Discovery: `autodiscover` and `bootstrap`

Idunn registers nothing on import. Decorators only attach metadata; one discovery call per process
imports your port and adapter modules so the decorated classes get catalogued. Both calls walk
`root_package` and import only modules whose dotted path contains a part named `port`, `ports`,
`adapter`, or `adapters`. Ports register before adapters, undecorated classes are ignored, and nothing
is constructed.

| Call | Use it when | Behavior |
|---|---|---|
| `Idunn().autodiscover('my_app')` | You own the process: an application with a `main()`, an app factory, or a startup hook. | Runs discovery each time it is called. Call it once at startup, before the first `@Invert()` object is built. |
| `Idunn().bootstrap('my_lib')` | You ship a library and have no startup hook to call `autodiscover` from. | `autodiscover` guarded to run once per root. Call it from every public entry point: the first call discovers, later calls return the cached report. Thread-safe. |

### Applications

```python
from idunn import Idunn

Idunn().autodiscover('my_app')  # once, at startup
app = MyApp()  # MyApp.__init__ is @Invert()-decorated; the graph wires itself
```

### Libraries

A library is imported, not started, and discovery at import time is a side effect nobody asked for.
Put `bootstrap` inside the library's own entry points so wiring happens the first time anyone uses it:

```python
from idunn import Idunn


class Engine:
  """Example engine class"""
  ...

class MyLib:
  """Public entry point; wires my_lib on first use."""

  def __init__(self) -> None:
    Idunn().bootstrap('my_lib')  # discovers once; a cheap no-op afterwards
    self._engine = Engine()  # an @Invert()-decorated worker
```

Both calls return a `ReportMap` listing the modules imported and the classes registered, handy for a
startup log. Discovery accumulates, so an application calls `autodiscover` for its own package and
any library it uses still bootstraps itself.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Normal usage

Put ports in a module or package named `ports`, adapters in one named `adapters`, decorate the
consumer's constructor with `@Invert()`, discover once, then construct.

```text
my_app/
  __init__.py
  main.py
  ports.py
  adapters.py
```

```python
# my_app/ports.py
from typing import Protocol

from idunn import Port


@Port
class AppleBasketPort(Protocol):
  def take_apple(self) -> str: ...
```


```python
# my_app/adapters.py
from idunn import Adapter, LifecycleEnum

from .ports import AppleBasketPort


@Adapter(AppleBasketPort, lifecycle=LifecycleEnum.SINGLETON)
class GoldenAppleBasketAdapter(AppleBasketPort):
  def take_apple(self) -> str:
    return 'youth restored'
```


```python
# my_app/main.py
from idunn import Idunn, Invert

from .ports import AppleBasketPort

class Feast:
  basket: AppleBasketPort  # declared for the type checker; @Invert assigns it

  @Invert()
  def __init__(self, basket: AppleBasketPort, host: str) -> None:
    self.host = host  # self.basket is injected and assigned for you

  def serve(self) -> str:
    return f'{self.host}: {self.basket.take_apple()}'


Idunn().autodiscover('my_app')
print(Feast(host='Bragi').serve())  # Bragi: youth restored
```

A runnable version lives in `examples/`: `python -m examples.basic_usage`.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## The three decorators

### `@Port`

Marks a `typing.Protocol` as a contract. Anything that is not a Protocol raises `InvalidPortError`.
The Protocol is made `runtime_checkable` so Idunn can confirm an adapter satisfies it.

### `@Adapter(port, lifecycle=...)`

Declares a concrete class as the implementation of `port`. It attaches metadata and constructs
nothing. The class must satisfy the Protocol, by inheritance (recommended) or structurally; Idunn
never patches it to fit. One adapter per port is the normal case. `lifecycle` is `TRANSIENT` by
default (a new instance per resolve) or `SINGLETON` (built once, reused).

Selecting between several adapters with `key=` and `envs=` is covered in
[Advanced](./docs/ADVANCED.md#choosing-between-adapters).

### `@Invert()`

Wraps a consumer's `__init__`. Every parameter whose type hint is a `@Port` is resolved when the
constructor runs, assigned to `self.<name>`, and passed into the body. Three things to know:

- A caller-supplied argument always wins, so `Feast(basket=fake, host='x')` skips injection and keeps
  the class easy to test.
- Resolution is recursive: an adapter's own `@Port` constructor parameters are resolved first.
- Constructing an `@Invert()` object is the only way to start a graph. There is no `resolve()`.

Always apply it with parentheses. Keyed selection, explicit parameter maps, and optional dependencies
are in [Advanced](./docs/ADVANCED.md#the-invert-contract-in-full).

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## What gets registered

Only classes wearing the badge. A class that satisfies a port but lacks `@Adapter(...)` is invisible
to discovery, and a module outside the `ports`/`adapters` naming rule is never imported. Looking the
part is not the same as wearing the badge.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Development

```bash
poetry install --with dev
poetry run pytest
poetry run ruff format --check . && poetry run ruff check .
poetry run mypy
```

CI (`.github/workflows/ci.yml`) runs the same checks. Idunn requires Python 3.13
(`>=3.13.16,<3.14.0`, pinned in `pyproject.toml`).

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Going further

- [About Idunn](./docs/ABOUT.md): the model and the reasons behind the short "no" list.
- [Advanced](./docs/ADVANCED.md): environments and keys, the full `@Invert` contract, discovery
  options, `describe()`, test isolation, exceptions, limitations, and maintainer notes.
- [Class catalog](./docs/classes.md): every class in the package, public or hidden.
