# Changelog

Notable changes to Idunn, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/), which is why a release that tightens this many rules is
2.0 and not 1.1. Releases up to 1.0.1 came before this file; their story lives in the git tags.

## 2.0.0 - 2026-11-05

Idunn grows up without growing out. The public surface is still three decorators, `Idunn`,
`LifecycleEnum`, `ReportMap` and seven exceptions, plus one test helper in its own package. The
work is underneath. Registration, singleton construction and `bootstrap` are now safe to hit from
many threads at once. A wrong `@Invert` declaration fails at import, next to its culprit, instead of
at the first unlucky call. And `@Invert()` now injects into plain functions as well as
constructors. For most code, upgrading from 1.0.1 means putting a `*` in front of the port
parameters. The list below covers everything else that might bite.

### Breaking changes

1. **Port parameters are keyword-only wherever `@Invert` applies.** That covers a consumer's
   constructor, a plain function, method or static method, and an adapter constructor that wears
   its own `@Invert(...)`. Mapped and keyed parameters count as ports. A port declared positionally
   raises `TypeError` at decoration, or at the first call when its hint is a forward reference that
   cannot resolve yet. Fix: declare the ports after `*`. Undecorated adapter constructors are
   exempt, since the resolver passes every port by keyword anyway.
2. **Extra positional arguments raise `TypeError`** before anything is injected, for `@Invert`
   constructors and functions alike. Before, they bound into port parameters, which is how
   `Feast('Bragi', 'a pear')` used to end up holding a pear where its basket should be.
3. **A map entry on a port-annotated parameter raises `InvalidPortError`.** Before, the map entry
   was ignored, so one of the two declarations was quietly a lie.
4. **More `@Invert` mistakes fail at decoration:**
   - an unknown map or `keys` name raises `TypeError` (it was `KeyError`, or silently ignored);
   - a key that is not a `str` raises `TypeError` (a `StrEnum` member is a `str`, and works);
   - a map value that is not a port raises `InvalidPortError` (it was the same error but only at
     the first call, an `AttributeError` for a non-class, or a silent default when the parameter
     had one);
   - `keys` on a parameter that is not a port raises `InvalidPortError`;
   - `@Invert()` on anything without a code object (a class, a builtin), or above `@staticmethod`
     or `@classmethod` rather than beneath it, raises `TypeError`.
5. **An adapter constructor's own `@Invert(keys=...)` or explicit map is honoured** when the
   resolver builds that adapter as someone else's dependency. Before, it got the unkeyed adapter,
   `AdapterNotFoundError` or `MissingTypeHintError`, depending on its luck.
6. **`Idunn()` takes no arguments.** `Idunn(environment=...)` raises `TypeError`, because a
   singleton would honour the argument once and ignore it forever after. Choose the environment
   with `Idunn().reset(environment=...)` or `IDUNN_ENV`.
7. **Stacked decorators are refused.** A second `@Adapter` on one class raises
   `InvalidAdapterError`, and a second `@Invert` on one function raises `TypeError`: only one
   declaration could ever win, so one of the two lines was always wrong. A decorated subclass is
   still fine.
8. **A root that does not live in directories raises `DiscoveryError`**, whatever `strict` says:
   a package imported from a zip, an egg or some frozen bundles. Before, discovery registered the
   root module's own classes and silently found nothing else.
9. **Error messages name things as `module.QualName`**, and anything without a qualified name
   (parameterized aliases such as `Repo[User]` included) by its `repr`. Message text changed
   throughout, so code that matches on it must update. `Port(5)` and `Adapter(5)` raise
   `InvalidPortError` instead of an `AttributeError` from the message itself, and so does
   `Port(SomeProtocol[int])` instead of a `TypeError` from `issubclass`.
10. **A `bootstrap` made while a module is being imported no longer waits** for another thread's
    discovery. It runs its own and returns its own run's report; every other caller gets the
    cached, merged one. One consequence: when two roots bootstrap each other from two threads,
    Python's import machinery may break the tie itself, and one call sees the failed import (a
    `DiscoveryError` under `strict=True`). 1.0.1 ran every root's discovery behind one lock, which
    ruled that out and made the import-time deadlock below possible instead. A retry is safe, and
    its report is complete.
11. **Discovery registration is atomic.** A collision raises `InvalidAdapterError` and leaves the
    catalog exactly as it was. Before, every class registered ahead of the collision stayed
    registered.
12. **The cached `bootstrap` report covers every run** of the root's first bootstrap, re-entrant
    and import-time runs included. A class defined after a re-entrant call is now listed. Before,
    it was registered but missing from the report, so `describe()` and the report disagreed and
    the report was the one telling fibs.
13. **Adapter keys and environment names are type-checked.** `@Adapter(key=...)` with a key that
    is not a `str` raises `TypeError`, the rule `@Invert(keys=...)` and `Harness.override(key=...)`
    apply too. Before, it registered an adapter nothing could ever ask for. An environment name
    that is not a `str` (`reset(environment=5)`, `@Adapter(envs={5})`) raises `ValueError`, as a
    malformed one always did, instead of an `AttributeError` about `strip`.

### Added

- **`idunn.testing.Harness`**, for wiring fakes into a test without the wiring outliving it.
  `install(*adapters)` registers adapters as one atomic batch, and `override(port, instance, *,
  key=None)` makes a port resolve to a stand-in ahead of any adapter, in any environment. Both are
  context managers and decorators, and on exit they restore registrations, singletons, overrides,
  `bootstrap` reports and the environment. `reset()` clears overrides too. Blocks unwind last in,
  first out, and a hand-driven outer block exiting before an inner one raises `RuntimeError`
  instead of leaking: it restores nothing, and the inner block's exit puts back what the outer one
  found.
- **`@Invert()` on plain functions, methods and static methods.** The ports arrive as keyword
  arguments at call time and nothing is assigned anywhere. Every other `@Invert` rule applies
  unchanged.
- **`@Invert(bootstrap='my_lib')`, so a library wires itself on first use** without an
  `Idunn().bootstrap` call in every entry point. A call that leaves at least one port parameter to
  injection, an optional one included, first runs the public `Idunn().bootstrap('my_lib')`: after
  the positional check and the plan, before anything is injected or assigned, once per call at
  most. So it is cached per root, shared by concurrent first calls and safe at import time, and a
  failure propagates and is retried by the next call. A call that brings every port discovers
  nothing, and the resolver, which passes an adapter constructor every port, never sets one off.
  A root that is not a non-empty `str`, or `bootstrap=` on a function with no port parameters,
  raises `TypeError`, and a `str` that is not a dotted run of identifiers (`'.relative'`,
  `'my lib'`, `'a..b'`) raises `ValueError`, judged from the spelling, with nothing imported or
  looked up. The `mead` library in the complex examples now wires itself this way, and a
  `bootstrap` call for a cached root is now one dictionary read, with no discovery callable built.
- **Forward and self references** in `@Invert` constructors and functions (`parent: Node | None`
  inside `Node`), under `from __future__ import annotations` or on 3.14 without it. Shape checks
  still run at decoration; the few that need the hints wait for the first call.
- **Thread safety beyond `bootstrap`, the only part 1.0.1 locked:**
  - catalog reads are copy-on-write and never lock, and discovery registration is linear in the
    classes found;
  - each `SINGLETON` is built once even when threads race for it, under a lock of its own, and the
    warm path is still one dictionary lookup;
  - a dependency cycle between singletons raises `InjectionCycleError` before any lock is taken,
    even when two threads race it, so it can never leave each thread holding half the cycle.
- **Faster transient chains.** Each adapter's constructor plan is worked out once and cached until
  `reset()`. Constructing an `@Invert()` consumer over a two-deep `TRANSIENT` chain went from
  70.0 to 9.4 µs on 3.11 (7.4x), 54.4 to 4.1 µs on 3.13 (13.2x) and 60.4 to 4.2 µs on 3.14
  (14.3x).
- **Python 3.14**, and the `Typing :: Typed` classifier. The status is now Beta.

### Changed

- **Some errors arrive earlier.** A loop through a singleton, or a planning error
  (`MissingTypeHintError`, a positional-only port) anywhere below a singleton's first build, is now
  reported before any constructor in that graph runs. Before, `TRANSIENT` dependencies earlier in
  the plan were built first. The exception types are the same; only the timing moved.
- **Enum keys are kept as their plain value.** `@Adapter(key=...)`, `@Invert(keys=...)` and
  `Harness.override(key=...)` store a `StrEnum` or `(str, Enum)` member as the string it stands
  for, so `describe()` and error messages print `key='gold'` rather than
  `key=<Grade.GOLD: 'gold'>`. Matching is unchanged: the member and its string find the same
  adapter, as before.
- **A positional-only port on an adapter constructor** raises `TypeError` naming
  `module.Adapter.param` when the adapter is first built, rather than Python's own complaint about
  a positional-only argument passed by keyword.
- **An adapter constructor hint that does not resolve** (a port defined inside a function under
  `from __future__ import annotations`, say) raises `MissingTypeHintError` naming the adapter and
  the missing name, chained from the `NameError`, instead of that bare `NameError` from deep inside
  `typing`. Nothing is cached, so the build succeeds once the name exists. An `@Invert` consumer
  still waits for its own forward references, as before.

### Fixed

- **Import-time `bootstrap` no longer deadlocks** against another thread's discovery. No Idunn
  lock is held while modules import, and a thread that may hold an import lock never waits for
  another thread's discovery.
- **A loop through an `@Invert()` consumer created inside a singleton's constructor** now raises
  `InjectionCycleError`, on one thread or several, instead of the `RecursionError` 1.0.1 gave on
  every thread involved. A loop made only of `TRANSIENT`s, closed by a consumer built inside one of
  their constructors, still ends in `RecursionError`. No lock is involved there, so it cannot hang.

### Tooling

- `bin/devtool` stays, and its `test` commands now tell the truth. `all` runs every test,
  `integration` selects the new `integration` marker and `unit` runs the rest, and each exits 1
  when tests fail; they used to exit 0 and announce success regardless, which is optimism rather
  than testing. `test all` also runs the suite a second time, on the newest pyenv CPython 3.14 in
  `tmp/venv-3.14`, because two `@Invert` contract tests only mean anything under PEP 649.
  `pytest-xdist` joined the dev group, so `test --parallel` (`-n auto`) runs on both. So did
  `pytest-timeout`, set to 120 seconds a test: a hang that never waits on anything, which no
  in-test deadline can catch, now fails its test instead of the afternoon. `test lint` is the one
  lint command, Ruff's linter and formatter and then mypy, and `test all` runs it first. It replaces
  `build lint` and `quality lint`, so the `quality` group is gone; its `completion` and `diagnose`
  commands drove examples that no longer exist. So is the unread `bin/requirements.txt`. Every
  command now runs from the repository root, so linting type-checks again and the "Error getting
  proj_root" line no longer greets every run, and a step that fails now counts as failed: the old
  `quality lint` passed a tree Ruff had just refused, and `build`, `project commit` and `project
  autotag` carried on past a failed step. Devtool itself works from any directory, reading
  `pyproject.toml` and cleaning at the repository root it finds beside itself, and `build clean`
  empties `tmp/` but spares the test venvs (`tmp/venv-*`) and `tmp/.gitkeep`, so a clean no longer
  costs a pyenv rebuild. It removes a symlink as a link and leaves whatever lies behind one alone,
  so a clean stays inside the repository.
- `poetry.lock` is committed. CI is split into a `quality` job, run once on
  3.13.16 (lock check, format, lint, strict mypy), and a `test` job on 3.11, 3.12, 3.13.16 and 3.14.
- The mypy cache joins Pytest's and Ruff's under the git-ignored `tmp/`. The unused `pillow` and
  `poetry-dynamic-versioning` dev dependencies and the redundant license classifier are gone. The
  sdist now carries this file.
- `examples/my_app` became four examples, `examples/{classy,functional}/{simple,complex}`, one
  pair with consumer classes and one with consumer functions. The suite runs every one and checks
  each line it prints, and the README's "Normal usage" listings are pinned to
  `examples/classy/simple`, so neither can drift from the code. Each example's docstring declares
  its `Environments:`, and a missing or stray `expected*.txt` fails, as does a class that moves
  module, since `Registers:` names classes relative to the example package.
- The README's links are absolute GitHub URLs, so they still work where PyPI renders it.

### Internal

None of this was ever public; it is listed for anyone who reached in anyway.

- **Removed:** `RegistrationKey`, `AdapterMetadata.order`, the mapper's selection memo,
  `Idunn._has`, `DecoratorSupport.extract_port_parameters`, `InversionResolver.resolve` and its
  four construction helpers, `AutoDiscovery`'s module-object root (`Idunn().autodiscover`
  always took a dotted name), and the mapper's `register_port`, `register_adapter`, `ports` and
  `select`: everything registers through `register_batch`, and the resolver now owns the selection
  rule and its `AdapterNotFoundError`.
- **The adapter stamp** is the `AdapterDeclaration` itself, under `__idunn_adapter__`. The boolean
  `__idunn_adapter__` flag and the separate `__idunn_adapter_declaration__` attribute are gone,
  and discovery and registration both read the stamp from the class's own `__dict__`, so an
  undecorated subclass of an adapter is no adapter to either.
- **New:** `Catalog`, `EngineSnapshot`, `FunctionShape`, `InvertDeclaration` and `ParameterPlan`
  in `domain`; `ConstructorPlanner`, `LazyPlan`, `BootstrapGate`, `BootstrapFlight`,
  `ReportMerger`, `ConstructionStack` and the `SingletonGeneration` and `BootstrapGeneration`
  named tuples in `internal`; `ImportContext` and `KeyedLocks` in `util`.
- `AutoDiscovery` takes its mapper once, at construction: the facade builds one beside the
  resolver, and `reset()` empties the mapper it shares rather than replacing either.
- `@Invert` reaches the engine through one private door, `Idunn()._inject(parameter)`, and
  `Harness` through four more (`_snapshot`, `_restore`, `_install`, `_override`). The mapper,
  resolver and bootstrap gate swap whole generations on `reset()` instead of emptying them, so a
  build or discovery racing a reset lands in the one being thrown away.
- The test suite dropped its `Container` seam and uses `Harness`, the same door users have.
