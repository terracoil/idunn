# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Package layout

`idunn/` is organized into four layers: `app/` (the `@Port`/`@Adapter`/`@Invert` decorators + the
`Idunn` facade), `domain/` (declaration/metadata, errors, `LifecycleEnum`, `RegistrationKey`,
`ReportMap`, `PortBinding`), `internal/` (the inversion engine — `InversionMapper`,
`InversionResolver`, `InversionValidator` — plus autodiscovery and decorator support), and `util/`
(`Environment`, `MetaSingleton`). `tests/test_architecture.py` enforces the allowed import
directions: app → any; domain → util; internal → domain/util; util → nothing internal.

## Commands

Tooling is Poetry-based. `bin/devtool` (a [Freyja](https://pypi.org/project/freyja/) CLI) is the primary entrypoint for development work; the raw Poetry
commands it wraps are also fine to use directly.

```bash
poetry install --with dev                 # or: bin/devtool setup env

poetry run pytest                         # all tests        (bin/devtool test all)
poetry run pytest tests/test_injection.py -k <name>   # a single test
poetry run ruff check .                    # lint            (bin/devtool quality lint)
poetry run ruff format --check .           # format check    (bin/devtool quality lint --fix to autofix)
poetry run mypy                            # strict type-check
poetry build                               # build           (bin/devtool build compile)
```

CI (`.github/workflows/ci.yml`) runs format-check + lint + mypy + pytest across Python
3.11–3.14. Target runtime is `>=3.11,<4.0`. The package lives at `idunn/` (repo root); there
is no `src/` layout despite the name of some legacy config keys.

## Architecture

Idunn is a constructor-time IoC toolkit. The model is **Port → Adapter → `@Invert` consumer**, with
the `Idunn` facade as a thin front for the engine:

- **`@Port` / `@Adapter` / `@Invert`** all live in `idunn/app/decorators.py`.
  - `@Port` marks a `typing.Protocol` as an injectable contract.
  - `@Adapter(port, *, key=None, lifecycle=LifecycleEnum.TRANSIENT, envs=None)` marks a
    concrete class as an implementation; declaration/metadata are frozen dataclasses in `idunn/domain/`.
    Unkeyed adapters answer unkeyed resolution; keyed adapters are opt-in (reachable only by their key).
  - `@Invert` wraps a *consumer's* constructor: every `@Port`-typed parameter is resolved at
    construction time and assigned to `self.<name>` (a caller-supplied arg overrides). A parameter
    typed `Port | None`, or any `@Port` param with a default, is **optional** — a missing adapter
    yields the default/`None` instead of raising. Annotation→port resolution (incl. unwrapping
    `Optional`) lives in `DecoratorSupport.port_from_annotation`.
- **`Idunn`** (`idunn/app/idunn.py`) is a thin **facade** — a process-wide singleton via
  `metaclass=MetaSingleton` (`idunn/util/meta_singleton.py`). Its public surface is just
  `autodiscover()` and `reset()` (plus `describe()` for introspection). It owns one `InversionMapper`
  and one `InversionResolver` and delegates to them; `@Invert` reaches resolution through the private
  `Idunn()._inject` / `Idunn()._has`. `Idunn().reset(environment=...)` clears state and rebinds the env.
- **The engine lives in `idunn/internal/`:** `InversionMapper` (catalog + env-filtered selection +
  a lazily-memoized `(environment, RegistrationKey)→AdapterMetadata` cache, invalidated on any
  registration), `InversionResolver` (recursive construction, cycle detection, `SINGLETON` instance
  cache), and the stateless `InversionValidator`. There is **no public `resolve()`** — resolving a
  port by hand was removed deliberately (see `docs/ADVANCED.md`); the only construction trigger is
  calling an `@Invert`-decorated constructor.

Key invariant: **decorators only attach metadata — they construct nothing.** `autodiscover()`
(`idunn/internal/auto_discovery.py`, class `AutoDiscovery`) only imports modules; objects are
instantiated only when an `@Invert`-decorated constructor runs.

Resolution (`InversionResolver._resolve` → `_construct`) is recursive and constructor-time:

1. ask `InversionMapper.select` for the active adapter for the requested port (precedence below);
2. inspect the adapter's `__init__`; each `@Port`-annotated parameter is resolved recursively. A
   `Port | None` param (or any `@Port` param with a default) is **optional** — a missing adapter
   yields the default/`None` instead of raising. The resolver and `@Invert` share the same
   annotation→port logic (`DecoratorSupport.port_from_annotation`), so optional deps behave
   identically at adapter constructors and consumer constructors;
3. a constructor param with no type hint and no default raises `MissingTypeHintError`;
4. re-entry into an adapter already under construction raises `InjectionCycleError`;
5. `LifecycleEnum.SINGLETON` adapters are cached; `TRANSIENT` are rebuilt each resolve.

### Adapter selection precedence

Two rules, both filtered by the active environment: an explicit key (`@Invert(keys=...)`) selects
that keyed adapter; with no key, resolution returns the single active *unkeyed* adapter (none
registered → `AdapterNotFoundError`, unless the consumer parameter is optional). Keyed adapters are
opt-in and never answer an unkeyed resolve.

### Environments

`Environment` (`idunn/util/environment.py`) resolves the active env from `Idunn().reset(environment=...)`,
then `IDUNN_ENV`, defaulting to `local` (normalized lowercase, `_`→`-`). `envs=None` means active
everywhere. Two adapters sharing a port and key (unkeyed counts as `key=None`) that are active in
overlapping environments raise `InvalidAdapterError`.

### AutoDiscovery boundary

`Idunn().autodiscover(root_package)` is bounded: it only imports modules whose dotted name contains an
exact part of `port`, `ports`, `adapter`, or `adapters`; ports register before adapters; undecorated
classes are never registered. It returns a **`ReportMap`** — a `TypedDict` of strings/string-tuples
(`idunn/domain/report.py`), not a class (there is no `DiscoveryReport`).

The public API is re-exported from `idunn/__init__.py` (the three decorators, `Idunn`,
`LifecycleEnum`, and the `IdunnError` hierarchy — nothing else). `examples/` is a discoverable
package; run it with `python -m examples.basic_usage` (the `examples.orchard` subpackage holds the
`ports`/`adapters`, and the runner demonstrates the `autodiscover` + `@Invert`-root workflow).

## Code style

Enforced here (beyond the global Python rules): single return point per function (guard clauses
excepted), 2-space indentation, full type hints, strict mypy. Behavior is encapsulated in classes — no
loose module-level functions; the `@Port`/`@Adapter`/`@Invert` decorators are the deliberate exception.

Returns are expressions: never `result = X; return result`, never `r = default; if c: r = Y; return r`
— write `return X` / `return Y if c else default`. A `result` variable is only acceptable as a genuine
accumulator (assigned on multiple branches or built across a loop, then returned once). See the global
*Single Return Point* + *No Unnecessary Variable Assignment* rules. Note: this repo uses Ruff (default
`F`/`I`/`D`/`B` rules) — `from x import *` is rejected (`F403`), so the global ">5 imports → `*`"
heuristic does not apply; use explicit imports + `__all__`.
