<!--
═══════════════════════════════════════════════════════════════════════════════
  CLAUDE — SELF-UPDATE RECIPE FOR THIS FILE  (docs/classes.md)
  Hidden from rendered Markdown; meant only for the agent maintaining this doc.

  TRIGGER. When the user says "update classes.md", "update the class catalog",
  "regenerate the catalog", or anything equivalent, follow this recipe top to
  bottom. Re-scan the source EVERY time — never hand-patch from memory, because
  the whole point of this file is that it tracks the code, not the other way around.

  STEP 1 — SCAN. Enumerate every class / Protocol / @dataclass / Enum / TypedDict /
    exception defined under idunn/ (all four layers: app/, domain/, internal/,
    util/, plus the testing/ barrel) and under examples/. A quick sweep:
        grep -rn '^class \|^  class \|^    class ' idunn/ examples/
    Then read idunn/__init__.py and idunn/testing/__init__.py (their __all__) to
    see what is actually exported; both barrels count as Public.
    Every class the sweep finds gets a row; util/ helpers are easy to miss.

  STEP 2 — CLASSIFY each class on two axes, using plain words (no emoji):
    • Audience:  Public  — in idunn/__init__.py __all__; meant to be used/caught.
                 Mixed   — not exported, yet reaches users anyway (e.g. a type
                           reachable through a public return value), so it is a
                           de facto API without being a headline one.
                 Hidden  — internal plumbing; never imported by end users. Being
                           re-exported from a layer package (idunn.domain etc.)
                           does not make a class Mixed.
    • Nature:    Passive — dataclass / enum / exception / TypedDict / Protocol
                           (holds shape, not behavior).
                 Active  — validates / resolves / scans / constructs / orchestrates.

  STEP 3 — GROUP into the sections below, keeping layer order app → domain →
    internal → util: Public API surface · Decorators · Testing · Definitions &
    metadata · Exceptions · Engine & orchestration · Examples. Add or drop a section only if
    a whole area appears or disappears in the code.

  STEP 4 — COLUMNS per table: Class | Nature | Purpose | Audience | Splittable? |
    Generic utility?
    • Purpose      — one tight sentence: WHAT it does + any load-bearing invariant.
    • Splittable?  — only meaningful for Mixed rows (how it could split public/hidden).
    • Generic utility? — "Yes" (or "Minor") when (part of) it is a reusable,
                         project-agnostic helper; "—" otherwise.

  STEP 5 — SYNC CHECK against the previous version of this file:
    • new classes → add rows; removed classes → delete rows; renamed → rename.
    • if __all__ changed, re-derive every Public/Mixed/Hidden mark.
    • RE-READ the decorator signatures so Purpose text matches current params —
      e.g. @Adapter currently takes key / lifecycle / envs and has NO `default`.
    • RE-READ each helper class's public methods (DecoratorSupport, Idunn) so the
      method lists in Purpose are complete.
    • compare the Exceptions table with the "Exceptions" table in ADVANCED.md and
      the docstrings in idunn/domain/errors.py; all three must agree.
    • spot-check the Examples section against examples/*/*/ specifically (one row
      per class, sub-packages included; the functional consumers are functions, so
      they appear in Purpose text, not as rows); it drifts most often.

  STEP 6 — Keep the `---` + apple-image separator between every `##` section, and no
    emoji in headings, tables, the legend or bullets. Preserve the two legends and the
    "Reading the catalog" closing notes (refresh their wording if the splittable/reusable
    story actually changed), and KEEP THIS COMMENT BLOCK intact at the top so the next
    update is just as cheap.

  SOURCES OF TRUTH to verify against:
    idunn/__init__.py · idunn/testing/__init__.py · idunn/app/port.py ·
    idunn/app/adapter.py · idunn/app/invert.py · idunn/app/idunn.py · idunn/app/harness.py ·
    idunn/domain/* · idunn/internal/* · idunn/util/* · examples/*/*/ (recursively)
═══════════════════════════════════════════════════════════════════════════════
-->

# Idunn Class and File Catalog

A map of every class defined in the live `idunn/` package and the runnable `examples/`. Use it to
tell at a glance what is part of the public contract, what is plumbing, and what could be tightened.
The package is split into four layers, `app/`, `domain/`, `internal/` and `util/`, plus a
`testing/` package that only re-exports `Harness` and that no layer may import. The import
directions between them are enforced by `tests/test_architecture.py`, so the map and the territory
are at least required to agree on the borders.

> *This file is self-maintaining: say "update classes.md" and Claude re-scans the source and
> regenerates it from the recipe embedded at the top.*

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Legend

| Mark | Audience: *who is meant to see it* |
|------|-------------------------------------|
| **Public** | Part of the intended end-user API; exported and meant to be used or caught directly. |
| **Mixed** | Not exported, but reaches users anyway, for instance through a public return value. The **Splittable** column says how it could be divided. No class is Mixed today. |
| **Hidden** | Internal plumbing; never meant to be seen or imported by end users. |

| Mark | Nature |
|------|--------|
| **Passive** | A *definition*: dataclass, enum, exception, TypedDict, or Protocol. Holds shape, not behavior. |
| **Active** | *Does* something: validates, resolves, scans, constructs, orchestrates. |

- **Splittable?** Only meaningful for Mixed rows: could the class be cleanly divided into a public
  surface and a hidden remainder?
- **Generic utility?** "Yes" when the class, or an extractable part of it, is a reusable,
  project-agnostic helper.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Public API surface: `idunn/__init__.py`

`__init__.py` is the barrel that re-exports the public names in its `__all__`: the three decorators
(`Port`, `Adapter`, `Invert`), the `Idunn` facade, `LifecycleEnum`, the `ReportMap` TypedDict, and
the full `IdunnError` hierarchy. It contains no logic of its own (Public, Passive). Its sibling
barrel, `idunn/testing/__init__.py`, exports one name, `Harness`, for tests only; the root does not
re-export it, so `from idunn import *` never drags test tooling into an application. Everything
else stays home: from `domain/`, the `AdapterDeclaration`, `AdapterMetadata`, `Catalog`,
`EngineSnapshot`, `FunctionShape`, `InvertDeclaration`, `ParameterPlan` and `PortBinding` types;
all of `internal/` (`InversionMapper`, `InversionResolver`, `InversionValidator`,
`SingletonGeneration`, `ConstructionStack`, `ConstructorPlanner`, `LazyPlan`, `AutoDiscovery`,
`BootstrapGate`, `BootstrapGeneration`, `BootstrapFlight`, `ReportMerger`, `DecoratorSupport`,
`PortRegistry`); and all of `util/`
(`Environment`, `ImportContext`, `KeyedLocks`, `MetaSingleton`, `QualifiedName`). What users never
import, nobody has to keep compatible.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Decorators: `app/port.py`, `app/adapter.py`, `app/invert.py`

| Class / Symbol | Nature | Purpose | Audience | Splittable? | Generic utility? |
|----------------|--------|---------|----------|-------------|------------------|
| `Port` (`port.py`) | Active | Class-based decorator applied bare: `__new__` checks the target really is a Protocol (anything else, `Port(5)` included, raises `InvalidPortError`), records it in `PortRegistry` (only that exact class is a port), makes it `runtime_checkable`, and returns the Protocol itself, so no `Port` instance ever exists. | Public | — | — |
| `Adapter` (`adapter.py`) | Active | Class-based decorator applied with arguments: `__init__` validates the port and the key (a `str`, `StrEnum` members included, else `TypeError`) and freezes `key`/`lifecycle`/`envs` into an `AdapterDeclaration`; `__call__` stamps it onto the class (`AdapterDeclaration.attach`), refusing a class that already carries its own declaration (stacked `@Adapter`; a decorated subclass is fine). Unkeyed adapters answer unkeyed resolution; keyed adapters are opt-in. Constructs nothing. | Public | — | — |
| `Invert` (`invert.py`) | Active | Class-based decorator applied with parentheses (`@Invert()`; bare, it raises `TypeError`). `__init__` checks and freezes `keys=` (`str` values, `StrEnum` members included, else `TypeError`), an explicit `{param: Port}` map (port values, else `InvalidPortError`) and the keyword-only `bootstrap=` root (a non-empty `str`, else `TypeError`, whose dotted parts must all be identifiers, else `ValueError`, judged by `_root` from the spelling; never imported or looked up at decoration) into an `InvertDeclaration`; `__call__` refuses a second `@Invert` on one function (`TypeError`), runs `ConstructorPlanner`'s shape rules on the code object, plans eagerly through a `LazyPlan` (lazily when a hint is a forward reference), stamps the declaration on the wrapper and returns it. At call time, after the positional check and the plan and before anything is injected, a `bootstrap=` wrapper with at least one planned port missing from the call's keywords calls the public `Idunn().bootstrap(root)`, once per call at most; the resolver passes adapter constructors every planned port, so it never sets one off. On an `__init__` every `@Port` parameter the caller left out is resolved through `Idunn()._inject` and every port parameter is assigned to `self.<name>` before the body runs; on any other function (plain, method, static) the ports are passed as keyword arguments and nothing is assigned. Supports **optional** deps (`Port \| None` or a defaulted param gets the default or `None` when no adapter is active). A map entry on a port-annotated parameter raises `InvalidPortError`. Port parameters are keyword-only (`TypeError` at decoration otherwise), and a call with more positional arguments than `FunctionShape.positional_limit` raises `TypeError` before anything is injected. | Public | — | — |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Testing: `app/harness.py`, published as `idunn.testing`

| Class / Symbol | Nature | Purpose | Audience | Splittable? | Generic utility? |
|----------------|--------|---------|----------|-------------|------------------|
| `Harness` (`harness.py`) | Active | Scoped test wiring, imported as `from idunn.testing import Harness`. `install(*adapters)` registers adapters as one atomic batch (a collision raises `InvalidAdapterError` before the block runs, with nothing registered); `override(port, instance, *, key=None)` makes a `(port, key)` resolve to `instance` ahead of selection, in any environment and with no adapter registered, after checking the port (`InvalidPortError`), the key (`TypeError` unless a `str`) and the instance (`InvalidAdapterError`). `install` refuses a class that never wore `@Adapter` itself, an undecorated subclass of an adapter included, exactly as discovery skips it. Both are `@contextmanager` static methods, so they also decorate functions and re-enter per call. Each block takes an `EngineSnapshot` on entry and restores it on exit, error or not, so blocks nest and unwind last in, first out. That order is enforced: the open blocks' snapshots sit in a class-level stack (a block's depth is its token), and an outer block exiting before an inner one raises `RuntimeError` before restoring anything; the inner block's exit then unwinds through it to the outer block's own snapshot, so neither block's wiring outlives them. Process-wide, like the container it borrows. | Public | — | — |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Definitions and metadata: `domain/`

| File | Class | Nature | Purpose | Audience | Splittable? | Generic utility? |
|------|-------|--------|---------|----------|-------------|------------------|
| `lifecycle_enum.py` | `LifecycleEnum` | Passive | `StrEnum` of adapter lifecycles, `SINGLETON` and `TRANSIENT`, with lowercase values so `@Adapter(lifecycle='singleton')` also works. Passed by users to `@Adapter`. | Public | — | — |
| `report.py` | `ReportMap` | Passive | `TypedDict` returned by `autodiscover` and `bootstrap`: string tuples of module names and qualified class names (`root_package`, `imported_modules`, `skipped_modules`, `registered_ports`, `registered_adapters`). The two `registered_*` keys list only what that call newly registered, except that the report `bootstrap` caches merges every run of the root's first bootstrap. A plain dict, no `Any`. | Public | — | — |
| `adapter_declaration.py` | `AdapterDeclaration` | Passive | Frozen carrier of the options captured by `@Adapter` (`port`/`key`/`lifecycle`/`envs`), made before the decorator has even seen its class. Owns its stamp like `InvertDeclaration`: `attach(cls)` sets it as `__idunn_adapter__`, and `of(target)` reads it back from the target's own `__dict__` only, so an undecorated subclass inherits the attribute but not the badge. `@Adapter`, `AutoDiscovery` and `InversionMapper` all ask `of`, so discovery and `Harness.install` agree on who is an adapter. | Hidden | — | — |
| `adapter_metadata.py` | `AdapterMetadata` | Passive (with helpers) | Frozen record of one *registered* adapter, plus `is_available_in()` and `environment_label()`. No arrival order: validation never lets two adapters compete for one slot in one environment, and the catalog's insertion order already remembers who came first. Indexed by `Catalog` and carried inside `PortBinding`. | Hidden | — | — |
| `catalog.py` | `Catalog` | Passive (with helpers) | Frozen, copy-on-write snapshot of every registration: `ports`, `adapters` (insertion order is registration order) and `slots`, a read-only `(port, key)` → adapters index (`SlotKey` is its alias). `find()` filters one slot by environment; `empty()` and `freeze()` build one. `InversionMapper` swaps in a whole new catalog per batch, so readers never lock and never see half a batch. | Hidden | — | Minor: the copy-on-write snapshot pattern. |
| `engine_snapshot.py` | `EngineSnapshot` | Passive | Frozen picture of everything a `Harness` block can change: `environment`, `catalog`, `instances` (built singletons), `overrides`, and bootstrap's `reports` and `carried` runs. The catalog and overrides are immutable, so they are kept by reference; the mutable parts are copied on the way in, held behind read-only proxies, and copied again on the way out, so neither the next build nor an inner block can write into a snapshot an outer block still needs. Made by `Idunn()._snapshot()`, put back by `_restore()`. | Hidden | — | — |
| `function_shape.py` | `FunctionShape` | Passive (with helpers) | Frozen parameter layout read from `__code__`, `__defaults__` and `__kwdefaults__` only: positional (and positional-only) names, keyword-only names, `*args`, defaults, and `constructor` (the function's own name is `__init__`). `caller_positional`, `named` and `positional_limit` are what the shape rules and the wrapper need. Never evaluates an annotation, so it works on 3.14 with an unresolved forward reference, where `inspect.signature` raises. `of()` returns `None` for anything without a code object. | Hidden | — | Minor: a signature reader that never evaluates hints. |
| `invert_declaration.py` | `InvertDeclaration` | Passive (with helpers) | Frozen `ports` map and `keys` handed to one `@Invert(...)`, behind read-only proxies (`frozen()`), plus its `bootstrap` root (`None` for none), so it is the one record of what `@Invert` was told; `names` covers only the map and keys. `attach()` stamps it on the wrapper as `__idunn_invert__` and `of()` reads it back. The resolver reads it to honour an adapter constructor's own keys and map (never `bootstrap`, which only the wrapper uses), and `@Invert` reads it to refuse stacking. Says nothing about the function's shape, since one `Invert(...)` may decorate several functions. | Hidden | — | — |
| `parameter_plan.py` | `ParameterPlan` | Passive (with helpers) | One injectable port parameter: `name`, `port`, `key`, `optional` and `default` (`Parameter.empty` when there is none), plus `tolerant` and `fallback`. The unit the planner produces, the resolver caches per adapter, and `Idunn()._inject` takes. | Hidden | — | — |
| `port_binding.py` | `PortBinding` | Passive | Frozen snapshot of one port: its `selected` adapter for an environment (or `None`) and all its `adapters`. Built by `InversionMapper.bindings()` as the single source behind `describe()`, which returns a string, so the type itself never reaches users. | Hidden | — | — |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Exceptions: `domain/errors.py`

All are Public and Passive: users catch them. `IdunnError` is the shared base, so one `except`
covers the family.

| Class | Raised when |
|-------|-------------|
| `IdunnError` | Base for every Idunn error. |
| `InvalidPortError` | `@Port` is applied to anything but a Protocol (`Port(5)` included), an adapter names an unmarked port, an `@Invert` map value is not a port, a parameter is both port-annotated and mapped, `keys` names a parameter that is not a port, a non-port is resolved, or `Harness.override` is handed a non-port. |
| `InvalidAdapterError` | `@Adapter` is applied to a non-class or twice to one class, `Harness.install` is handed a class that never wore `@Adapter` (an undecorated subclass of an adapter included), two adapters share a port and key in overlapping environments (the batch that hits it, discovery's or `Harness.install`'s, registers nothing), or a built instance or a `Harness.override` stand-in does not satisfy its port. |
| `AdapterNotFoundError` | No active adapter is registered for a requested port and the parameter is not optional. |
| `DiscoveryError` | A module below the discovery root fails to import and `strict=True`, or, whatever `strict` says, the root has a `__path__` entry that is not a directory (a zip). The root's own import errors propagate unwrapped. |
| `MissingTypeHintError` | An adapter constructor parameter without a default has no annotation, or one that is not a port, or a constructor hint does not resolve (chained from the `NameError`). |
| `InjectionCycleError` | Constructor dependency resolution loops back on an adapter already under construction. A loop through a `SINGLETON` is found by a dry walk before anything is built, so threads racing one both raise instead of deadlocking. |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Engine and orchestration

| File | Class | Nature | Purpose | Audience | Splittable? | Generic utility? |
|------|-------|--------|---------|----------|-------------|------------------|
| `app/idunn.py` | `Idunn` | Active | Thin **facade** and process-wide singleton (`metaclass=MetaSingleton`); `Idunn()` takes no arguments, so the environment is chosen by `IDUNN_ENV` or `reset(environment=...)`. Public surface is `autodiscover()`, `bootstrap()` (a once-per-root `autodiscover` for library entry points, delegated to `BootstrapGate`), `reset()`, `describe()` and the read-only `environment` property; owns one `InversionMapper`, one `InversionResolver`, one `AutoDiscovery` (built once on that mapper) and one `BootstrapGate` and delegates. `@Invert` reaches resolution through one private door, `_inject(parameter)`, which takes a `ParameterPlan` and lets the resolver decide tolerance. `Harness` uses four more private hooks: `_snapshot()` and `_restore(snapshot)` (an `EngineSnapshot` across the mapper, resolver, gate and environment) and `_install(adapters)` and `_override(port, instance, key=...)`. No public `resolve`/`register_*`, by design. | Public | — | — |
| `internal/inversion_mapper.py` | `InversionMapper` | Active | Owns the `Catalog`. Writes go through `register_batch` (ports, then adapters), the only way in, under one write lock: copy once, skip what is already registered, validate each new adapter against its slot, swap once, so a batch lands whole or not at all; a class without its own `AdapterDeclaration` raises `InvalidAdapterError`. Reads (`find`, `bindings`, and the `catalog` property behind `Harness` snapshots) take one snapshot and never lock, and `bindings()` emits the `PortBinding`s behind `describe()`. `restore(catalog)` swaps back a catalog read earlier, for `Harness`, and `clear()` swaps in an empty one, for `reset()`. | Hidden | — | — |
| `internal/construction_stack.py` | `ConstructionStack` | Active (thread-local) | A `threading.local` holding `current`, the construction stack of the `SINGLETON` build running on this thread (class-level default `()`, so a thread that never published reads a plain attribute). `publishing(stack)` is a context manager that sets it for the build and restores the outer value, error or not. `inject` seeds from it, which makes a consumer built inside a constructor an ordinary edge for the cycle walk and the stack check; a worker thread a constructor starts begins empty. Published around singleton builds only, for speed. Not re-exported from `idunn.internal`. | Hidden | — | — |
| `internal/inversion_resolver.py` | `InversionResolver` | Active | The construction engine: recursive, plan-driven resolution, the in-progress cycle stack, the `SINGLETON` instance cache and a per-adapter-class plan cache (`_plans`, filled on first build by `ConstructorPlanner.plan_adapter`, dropped by `clear()`). `inject(parameter=...)` is the facade's door; adapter parameters go through the same private `_inject`, so a tolerant parameter with no active adapter gets its fallback in both places. One private `_choose` holds the selection rule (an override, else `InversionMapper.find`) for the build and the cycle walk alike, so the walk cannot see a different graph from the build, and a required parameter with nothing chosen raises `AdapterNotFoundError` naming port, key and environment; an adapter constructor's own `@Invert` keys and map are honoured, undecorated ones resolve unkeyed. Each `SINGLETON` is built once: the warm path is a lock-free lookup, and a miss runs a dry cycle walk (no construction, no lock; it follows the build's selections and raises `InjectionCycleError` for a loop) before building under the adapter's own lock from `KeyedLocks` and checking the cache again inside it. Its generation, a `SingletonGeneration` of `instances` and `locks`, is read once per `inject` and swapped whole by `clear()`, so a build racing `reset()` lands in the discarded one. A singleton build publishes its stack in a `ConstructionStack`, and `inject` starts from it, so an `@Invert()` consumer created inside the constructor continues the path and a loop through it raises `InjectionCycleError` (U16). Overrides (`override()`, for `Harness`, which refuses a non-`str` key) are a copy-on-write `(port, key)` mapping consulted ahead of selection and are leaves for the cycle walk; outside a `Harness` block there is no mapping at all (`None`), so the hot path pays one identity test. `snapshot()` returns a read-only copy of the singletons plus the overrides, and `restore(instances=..., overrides=...)` takes exactly those back: it puts the overrides back first (a resolve reads them live but captures its generation once), then installs a copy as a whole new generation with fresh locks, so a build racing it lands in the discarded one, as with `clear()`, which also drops overrides. | Hidden | — | — |
| `internal/singleton_generation.py` | `SingletonGeneration` | Passive (`NamedTuple`) | One generation of singletons: `instances` (built `SINGLETON`s per adapter class) and `locks` (the `KeyedLocks` guarding each first build). `InversionResolver` swaps it whole on `clear()` and `restore()`, and a resolve captures it once and hands it down, so a build racing a reset lands in the discarded one. Not re-exported from `idunn.internal`. | Hidden | — | — |
| `internal/constructor_planner.py` | `ConstructorPlanner` | Active (stateless) | The one rulebook for which parameters get injected. `check_shape()` applies the shape rules from the code object at decoration (a `staticmethod` or `classmethod` object and anything without a code object are refused, and every mapped or keyed name must be a parameter and keyword-only; all `TypeError`); `plan()` applies the annotation rules from the type hints (no map entry on a port-annotated parameter, `keys` on ports only; `InvalidPortError`) and builds the `ParameterPlan`s; `plan_adapter()` does the same for an adapter constructor and also refuses non-port parameters without defaults (`MissingTypeHintError`), positional-only ports (`TypeError`) and a constructor hint that does not resolve (`MissingTypeHintError` from `_adapter_hints`, naming the adapter and quoting the `NameError` it chains from; uncached, since the resolver keeps only plans that worked). `plan()` always requires port-annotated parameters to be keyword-only, since both wrappers read ports from `kwargs` alone, and `plan_adapter()` requires it of decorated constructors only; undecorated ones are exempt, because the resolver passes every port by keyword. | Hidden | — | — |
| `internal/lazy_plan.py` | `LazyPlan` | Active | One `@Invert` function's plan, kept in the wrapper's closure: `try_now()` plans at decoration and swallows only `NameError` (a forward reference), `get()` plans on first call if needed and never caches a failure, `ready` says which happened. It also holds the one rule that needs the finished plan: `bootstrap=` on a function with no port parameters raises `TypeError` (`_refuse_idle_bootstrap`), at decoration or, behind a forward reference, at every call until it resolves. | Hidden | — | — |
| `internal/inversion_validator.py` | `InversionValidator` | Active (stateless) | Stateless checks: `validate_adapter_class()` (adapter-class validity, a backstop for declarations attached without `@Adapter`), `validate_registration()` (duplicates within one `(port, key)` slot in overlapping envs, checked against that slot only, so validation stays linear) and `validate_instance()` (instance-satisfies-port). Called by the mapper and resolver; raises `IdunnError`s. Not re-exported from `idunn.internal`. | Hidden | — | — |
| `internal/auto_discovery.py` | `AutoDiscovery` | Active | Imports every module under a dotted root name (skipping `__main__`, non-identifier parts, test modules and `exclude` patterns; the running `__main__` is reused), then registers the decorated classes as one all-or-nothing batch into the `InversionMapper` it was constructed with (the facade builds one, on its own mapper, for life; `reset()` empties that mapper in place), ports first, and returns a `ReportMap`. A root whose `__path__` is not a directory (a zip) raises `DiscoveryError` whatever `strict` says; root import errors are not wrapped. Reached via `Idunn().autodiscover`. | Hidden | — | Yes: the module-scan helpers (`_module_names`, `_path_entries`, `_relative_parts`, `_is_excluded`, `_load`) are a reusable "find and import dotted modules under a package" utility. |
| `internal/bootstrap_gate.py` | `BootstrapGate` | Active (process-wide state) | Runs `bootstrap`'s discovery once per root and caches the report. Its `Lock` guards bookkeeping only, never an import. Entry-point callers that find a flight in progress wait on its `Event` and share one report; a thread that already has a run aboard (re-entry) and any thread with an import on its stack (`ImportContext`) join the flight and discover themselves instead, so nobody waits while possibly holding an import lock, or on itself. The last run out caches the `ReportMerger` merge; if the owner failed it caches nothing and carries the successful runs' reports into the retry's flight instead. `cached(root)` is the facade's warm path, one lock-free read that spares a cached root the `discover` callable. `clear()` swaps the reports, flights and carried runs as one `BootstrapGeneration`, and each run captures it once at entry; `snapshot()` hands out read-only copies of the reports and carried runs, and `restore(reports=..., carried=...)` swaps copies of exactly those back in the same way, with no flights. Reached via `Idunn().bootstrap`, `reset()` and `Harness`. | Hidden | — | Minor: a once-per-key, import-safe guard, but the merge ties it to `ReportMap`. |
| `internal/bootstrap_flight.py` | `BootstrapFlight` | Passive (frozen record) | One root's first bootstrap while runs are still in progress: `runners` (one thread ident per run in progress, so nested re-entries repeat and `aboard_here()` asks "does this thread have a run in flight?"), the `done` event, finished reports (starting from any a failed flight carried) and a failed flag. `launch()` opens one for the calling thread, `boarded()` and `leaving()` return it with a run added or finished, and `landed` says the last run is out. Replaced copy-on-write under the gate's lock. Not re-exported from `idunn.internal`. | Hidden | — | — |
| `internal/bootstrap_generation.py` | `BootstrapGeneration` | Passive (`NamedTuple`) | One generation of bootstrap memory, per root: `reports` (cached merged reports), `flights` (first bootstraps in progress) and `carried` (successful runs of failed flights, waiting for the retry). `BootstrapGate` swaps it whole on `clear()` and `restore()`, and each run captures it once at entry. Not re-exported from `idunn.internal`. | Hidden | — | — |
| `internal/report_merger.py` | `ReportMerger` | Active (stateless) | `merge()` folds the runs of one root's first bootstrap into one report: sorted union of `imported_modules`, `skipped_modules` minus anything another run imported, `registered_*` concatenated in run-finish order (exact, because each class is new for exactly one atomic batch). Not re-exported from `idunn.internal`. | Hidden | — | — |
| `internal/decorator_support.py` | `DecoratorSupport` | Active | Helpers shared by the decorators, the planner and the resolver: `normalize_envs()` (collapse `envs` into a normalized `frozenset`, or `None`), `plain_key()` (an adapter key as a plain `str`, via `str.__str__`, so a `StrEnum` or `(str, Enum)` member is kept, matched and printed as its value) and `port_from_annotation()` (resolve an annotation to `(port, optional)`, unwrapping `Port \| None`). | Hidden | — | Minor: tied to Idunn rules. |
| `internal/port_registry.py` | `PortRegistry` | Active (process-wide state) | `WeakSet` of the Protocols decorated with `@Port`: `mark()` records one, `is_port()` checks exact class identity. Replaces a marker attribute, which Python 3.11 would count as a protocol member and so break structural adapters. Subclasses of a port are not ports. | Hidden | — | — |
| `util/environment.py` | `Environment` | Active (value + logic) | Frozen value object holding a resolved env `name`, plus `current()` (resolve from argument, then `IDUNN_ENV`, then `local`) and `normalize()` (strip, lowercase, `_` to `-`, blank to `local`, then validate; a name that is not a `str` is a `ValueError` like any other bad name). Reached at `Idunn()` construction, on `reset()`, and when `@Adapter(envs=...)` is normalized. | Hidden | — | Yes: `normalize()` is a generic slug normalizer. |
| `util/import_context.py` | `ImportContext` | Active (stateless) | `active()` walks the current thread's frames for `<frozen importlib._bootstrap>`, which is on the stack whenever `importlib` holds a module lock, loaders' `exec_module` and C-extension init included (a stray match only costs a spare discovery). No frame support means `True`, the safe answer. Used by `BootstrapGate` to decide who must never wait. | Hidden | — | Yes: "am I inside an import?" is project-agnostic. |
| `util/keyed_locks.py` | `KeyedLocks` | Active (lock registry) | Generic `KeyedLocks[K]`: `for_key(key)` returns the same `RLock` for the same key, made on first request (a lock-free `dict.get`, then `setdefault` under a guard `Lock` on a miss, so two threads asking at once share one lock). Re-entrant so a holder coming back for its own key on the same thread fails loudly elsewhere rather than deadlocking on itself. Never drops a lock; the owner replaces the whole object to start over. Used by `InversionResolver` for one lock per `SINGLETON` adapter class. | Hidden | — | Yes: per-key locking is project-agnostic. |
| `util/meta_singleton.py` | `MetaSingleton` | Active | Metaclass that caches one instance per class, making `Idunn()` a process-wide singleton; double-checked locking keeps first construction race-free without locking every call after. `__call__` takes no arguments, because a singleton can only honor them once. | Hidden | — | Yes: a generic singleton metaclass. |
| `util/qualified_name.py` | `QualifiedName` | Active | Stateless `module.QualName` renderer, `of()`, for any object (`repr` for anything without a qualified name, and for parameterized aliases), used by every error message, discovery reports, `describe()` and binding sort order. | Hidden | — | Yes: a generic one-liner, small enough to forget it exists. |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Examples: `examples/`

Teaching code: Public as *documentation*, but not part of the importable library or the wheel.
Four packages, two trees (`classy/` consumers are classes, `functional/` consumers are functions)
of one simple and one complex example each, importing only from `idunn`. Each has a guarded
`main.py`, an `__init__` docstring whose `Registers:` line names, relative to the package
(`shop.till.Till`), what discovering it finds and whose `Environments:` line names its runs (`unset`
for the one with no `IDUNN_ENV`), and one `expected*.txt` per run with its exact output;
`tests/test_examples.py` holds every example to all three, a missing or stray expected file
included. Run one from the repo root with `poetry run python -m examples.<tree>.<name>.main`, the
complex ones under `IDUNN_ENV=local` or `prod`. Functions are not classes, so the functional
consumers appear in the purposes below, not as rows.

### `classy/simple`: the README's `my_app`

`main.py` discovers `'examples.classy.simple'` and prints `Bragi: youth restored`.

| File | Class | Nature | Purpose |
|------|-------|--------|---------|
| `classy/simple/ports.py` | `AppleBasketPort` | Passive | `@Port` Protocol: a contract with a single `take_apple()` method. |
| `classy/simple/adapters.py` | `GoldenAppleBasketAdapter` | Active | Unkeyed `@Adapter` (singleton) for `AppleBasketPort`; answers a plain `@Invert()`. |
| `classy/simple/main.py` | `Feast` | Active | Plain `@Invert()` root, `(self, host: str, *, basket: AppleBasketPort)`: the keyword-only port is injected and assigned to `self.basket` automatically, so `Feast('Bragi')` can only mean the host. |

### `functional/simple`: the same, without a class

The consumer is `feast(host: str, *, basket: AppleBasketPort) -> str` in `main.py`, an `@Invert()`
function that receives the basket as a keyword argument and keeps it nowhere. Same output.

| File | Class | Nature | Purpose |
|------|-------|--------|---------|
| `functional/simple/ports.py` | `AppleBasketPort` | Passive | Same as in `classy/simple`. |
| `functional/simple/adapters.py` | `GoldenAppleBasketAdapter` | Active | Same as in `classy/simple`; here it answers `feast`'s `basket`. |

### `classy/complex`: the shop

`main.py` autodiscovers only the application, `examples.classy.complex.shop`, then uses the `mead`
library, whose consumer bootstraps its own root, and prints `describe()` last. Under `local` and
`prod` the receipts, the skald and the `selected:` lines differ; `expected.local.txt` and
`expected.prod.txt` pin both.

| File | Class | Nature | Purpose |
|------|-------|--------|---------|
| `classy/complex/shop/ports.py` | `StoreroomPort` | Passive | `@Port`: `take(count)` and `remaining()`. One of five ports in one module, on purpose. |
| `classy/complex/shop/ports.py` | `PaymentPort` | Passive | `@Port`: `charge(customer, amount)`, with two adapters told apart by `envs=`. |
| `classy/complex/shop/ports.py` | `HeraldPort` | Passive | `@Port`: `announce(news)`. Only keyed adapters, so `describe()` shows `selected: <none>`. |
| `classy/complex/shop/ports.py` | `SagaPort` | Passive | `@Port`: `tell(deed)`, consumed as an optional `SagaPort \| None`. |
| `classy/complex/shop/ports.py` | `CheckoutPort` | Passive | `@Port`: `sell(customer, count)`. |
| `classy/complex/shop/stock_view.py` | `StockView` | Passive | Plain Protocol, deliberately not a port: `remaining()` only, the read-only hint an explicit map fills with `StoreroomPort`. |
| `classy/complex/shop/storeroom.py` | `Storeroom` | Active (state) | `SINGLETON` `StoreroomPort` holding six apples. Every till shares it, so stock carries over between sales; overselling raises `ValueError`. |
| `classy/complex/shop/rune_tally_payment.py` | `RuneTallyPayment` | Active | `PaymentPort` with `envs='local'`. |
| `classy/complex/shop/gold_coffer_payment.py` | `GoldCofferPayment` | Active | `PaymentPort` with `envs='prod'`. Never active alongside the rune stick, so an unkeyed resolve finds the stick in `local`, the gold in `prod`, and never both. |
| `classy/complex/shop/raven_herald.py` | `RavenHerald` | Active | `HeraldPort` with `key='raven'`. |
| `classy/complex/shop/gjallarhorn_herald.py` | `GjallarhornHerald` | Active | `HeraldPort` with `key='horn'`. |
| `classy/complex/shop/skald_saga.py` | `SkaldSaga` | Active | `SagaPort` with `envs='local'`; in `prod` the optional parameter receives `None`. |
| `classy/complex/shop/till.py` | `Till` | Active | `TRANSIENT` `CheckoutPort` whose undecorated constructor takes `StoreroomPort` and `PaymentPort` by keyword; takes the stock before the money. |
| `classy/complex/shop/stall.py` | `Stall` | Active | `@Invert(keys={'crier': 'horn'})` consumer, `(self, keeper: str, *, till, crier, saga: SagaPort \| None = None)`. |
| `classy/complex/shop/stocktaker.py` | `Stocktaker` | Active | `@Invert({'stock': StoreroomPort}, keys={'messenger': 'raven'})` consumer: the map fills a `StockView` hint. |
| `classy/complex/mead/ports.py` | `BrewPort` | Passive | The library's `@Port`: `draw()`. |
| `classy/complex/mead/brewery.py` | `KvasirBrewery` | Active | Unkeyed `@Adapter` for `BrewPort`. |
| `classy/complex/mead/cupbearer.py` | `Cupbearer` | Active | The library's internal consumer of `BrewPort`, and where it wires itself: `@Invert(bootstrap=ROOT)` (`ROOT = 'examples.classy.complex.mead'`) discovers the library the first time a cupbearer is hired without a brewery; later hires are a cache hit. |
| `classy/complex/mead/hall.py` | `MeadHall` | Active | The library's one export. It wires nothing itself: its constructor hires a `Cupbearer`, which bootstraps the library on first use, so a second hall is a cache hit. |

### `functional/complex`: the shop, as functions

The port implementations are copies of the classes in `classy/complex`, and the output is the same
apart from module paths. Every consumer is a function: `open_stall` (`keys={'crier': 'horn'}`),
`sell` (optional `saga`) and `take_stock` (the `StockView` map, `keys={'messenger': 'raven'}`) in
`shop/`, and in `mead/` the `@Invert(bootstrap=ROOT)` function `pour_for`, which wires the library
on its first call, behind `pour`, the entry point.

| File | Class | Nature | Purpose |
|------|-------|--------|---------|
| `functional/complex/shop/ports.py` | `StoreroomPort` | Passive | Same as in `classy/complex`. |
| `functional/complex/shop/ports.py` | `PaymentPort` | Passive | Same as in `classy/complex`. |
| `functional/complex/shop/ports.py` | `HeraldPort` | Passive | Same as in `classy/complex`. |
| `functional/complex/shop/ports.py` | `SagaPort` | Passive | Same as in `classy/complex`. |
| `functional/complex/shop/ports.py` | `CheckoutPort` | Passive | Same as in `classy/complex`. |
| `functional/complex/shop/stock_view.py` | `StockView` | Passive | Same as in `classy/complex`; filled for `take_stock`. |
| `functional/complex/shop/storeroom.py` | `Storeroom` | Active (state) | Same as in `classy/complex`; it outlives every call. |
| `functional/complex/shop/rune_tally_payment.py` | `RuneTallyPayment` | Active | Same as in `classy/complex`. |
| `functional/complex/shop/gold_coffer_payment.py` | `GoldCofferPayment` | Active | Same as in `classy/complex`. |
| `functional/complex/shop/raven_herald.py` | `RavenHerald` | Active | Same as in `classy/complex`. |
| `functional/complex/shop/gjallarhorn_herald.py` | `GjallarhornHerald` | Active | Same as in `classy/complex`. |
| `functional/complex/shop/skald_saga.py` | `SkaldSaga` | Active | Same as in `classy/complex`. |
| `functional/complex/shop/till.py` | `Till` | Active | Same as in `classy/complex`: a function form changes the consumers, not the adapters. |
| `functional/complex/mead/ports.py` | `BrewPort` | Passive | Same as in `classy/complex`. |
| `functional/complex/mead/brewery.py` | `KvasirBrewery` | Active | Same as in `classy/complex`. |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Reading the catalog

- **The public surface is tight.** Top-level `idunn` exports only the three decorators, `Idunn`,
  `LifecycleEnum`, the `ReportMap` TypedDict, and the exception hierarchy; `idunn.testing` exports
  `Harness` and nothing else. Nothing is Mixed: the engine-facing domain types
  (`AdapterDeclaration`, `AdapterMetadata`, `Catalog`, `EngineSnapshot`, `FunctionShape`,
  `InvertDeclaration`, `ParameterPlan`, `PortBinding`) never reach users, because the facade
  returns strings and reports rather than engine types. (The `InvertDeclaration` stamped on every
  `@Invert` wrapper as `__idunn_invert__` is reachable, but it is plumbing, not an API.)
- **Candidates for promotion.** `PortBinding` is the obvious one. It is a read-only snapshot that
  could become a public introspection type if `describe()` ever grows a structured sibling. Until
  someone asks, it stays a string.
- **Reusable bits worth extracting.** `MetaSingleton`, `Environment.normalize` (slug normalizer),
  `QualifiedName`, `KeyedLocks`, `ImportContext`, and `AutoDiscovery`'s module-scan helpers are
  the most project-agnostic code in the package.
- **Genuinely hidden classes.** The engine trio (`InversionMapper`, `InversionResolver`,
  `InversionValidator`), the planners (`ConstructorPlanner`, `LazyPlan`), the bootstrap quartet
  (`BootstrapGate`, `BootstrapFlight`, `ReportMerger`, `BootstrapGeneration`), plus
  `SingletonGeneration`, `ConstructionStack`, `AutoDiscovery`,
  `DecoratorSupport`, `PortRegistry` and every `util/` class, are never meant to be imported by
  end users. They sit behind the `Idunn` facade, which is where they are happiest. `Harness` is
  the one engine-facing class that is public, and it only borrows the facade's private hooks for
  the length of a `with` block.
