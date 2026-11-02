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
    util/) and under examples/. A quick sweep:
        grep -rn '^class \|^  class \|^    class ' idunn/ examples/
    Then read idunn/__init__.py (its __all__) to see what is actually exported.
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
    internal → util: Public API surface · Decorators · Definitions & metadata ·
    Exceptions · Engine & orchestration · Examples. Add or drop a section only if
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
    • spot-check the Examples section against examples/my_app/ specifically;
      it drifts most often (new demo classes get added there first).

  STEP 6 — Keep the `---` + apple-image separator between every `##` section, and no
    emoji in headings, tables, the legend or bullets. Preserve the two legends and the
    "Reading the catalog" closing notes (refresh their wording if the splittable/reusable
    story actually changed), and KEEP THIS COMMENT BLOCK intact at the top so the next
    update is just as cheap.

  SOURCES OF TRUTH to verify against:
    idunn/__init__.py · idunn/app/port.py · idunn/app/adapter.py · idunn/app/invert.py ·
    idunn/app/idunn.py ·
    idunn/domain/* · idunn/internal/* · idunn/util/* · examples/my_app/*
═══════════════════════════════════════════════════════════════════════════════
-->

# Idunn Class and File Catalog

A map of every class defined in the live `idunn/` package and the runnable `examples/`. Use it to
tell at a glance what is part of the public contract, what is plumbing, and what could be tightened.
The package is split into four layers, `app/`, `domain/`, `internal/` and `util/`, and the import
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
the full `IdunnError` hierarchy. It contains no logic of its own (Public, Passive). Everything else
stays home: from `domain/`, the `AdapterDeclaration`, `AdapterMetadata`, `Catalog` and
`PortBinding` types; all of `internal/` (`InversionMapper`, `InversionResolver`,
`InversionValidator`, `AutoDiscovery`, `BootstrapGate`, `BootstrapFlight`, `ReportMerger`,
`DecoratorSupport`, `PortRegistry`); and all of `util/` (`Environment`, `ImportContext`,
`MetaSingleton`, `QualifiedName`). What users never import, nobody has to keep
compatible.

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Decorators: `app/port.py`, `app/adapter.py`, `app/invert.py`

| Class / Symbol | Nature | Purpose | Audience | Splittable? | Generic utility? |
|----------------|--------|---------|----------|-------------|------------------|
| `Port` (`port.py`) | Active | Class-based decorator applied bare: `__new__` checks the target really is a Protocol (anything else, `Port(5)` included, raises `InvalidPortError`), records it in `PortRegistry` (only that exact class is a port), makes it `runtime_checkable`, and returns the Protocol itself, so no `Port` instance ever exists. | Public | — | — |
| `Adapter` (`adapter.py`) | Active | Class-based decorator applied with arguments: `__init__` validates the port and freezes `key`/`lifecycle`/`envs` into an `AdapterDeclaration`; `__call__` stamps it onto the class, refusing a class that already carries its own declaration (stacked `@Adapter`; a decorated subclass is fine). Unkeyed adapters answer unkeyed resolution; keyed adapters are opt-in. Constructs nothing. | Public | — | — |
| `Invert` (`invert.py`) | Active | Class-based decorator applied with parentheses (`@Invert()`). `__init__` captures `keys=` and an explicit `{param: Port}` map; `__call__` wraps a *consumer's* `__init__` so every `@Port`-typed parameter the caller left out is resolved through the `Idunn()` facade, and every port parameter is assigned to `self.<name>` before the body runs. Supports **optional** deps (`Port \| None` or a defaulted param gets the default or `None` when no adapter is active). A port annotation beats an explicit map entry for the same parameter. | Public | — | — |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Definitions and metadata: `domain/`

| File | Class | Nature | Purpose | Audience | Splittable? | Generic utility? |
|------|-------|--------|---------|----------|-------------|------------------|
| `lifecycle_enum.py` | `LifecycleEnum` | Passive | `StrEnum` of adapter lifecycles, `SINGLETON` and `TRANSIENT`, with lowercase values so `@Adapter(lifecycle='singleton')` also works. Passed by users to `@Adapter`. | Public | — | — |
| `report.py` | `ReportMap` | Passive | `TypedDict` returned by `autodiscover` and `bootstrap`: string tuples of module names and qualified class names (`root_package`, `imported_modules`, `skipped_modules`, `registered_ports`, `registered_adapters`). The two `registered_*` keys list only what that call newly registered, except that the report `bootstrap` caches merges every run of the root's first bootstrap. A plain dict, no `Any`. | Public | — | — |
| `adapter_declaration.py` | `AdapterDeclaration` | Passive | Frozen carrier of the options captured by `@Adapter` (`port`/`key`/`lifecycle`/`envs`), made before the decorator has even seen its class; the only consumer is `InversionMapper` at registration time. | Hidden | — | — |
| `adapter_metadata.py` | `AdapterMetadata` | Passive (with helpers) | Frozen record of one *registered* adapter, plus `is_available_in()` and `environment_label()`. No arrival order: validation never lets two adapters compete for one slot in one environment, and the catalog's insertion order already remembers who came first. Indexed by `Catalog` and carried inside `PortBinding`. | Hidden | — | — |
| `catalog.py` | `Catalog` | Passive (with helpers) | Frozen, copy-on-write snapshot of every registration: `ports`, `adapters` (insertion order is registration order) and `slots`, a read-only `(port, key)` → adapters index (`SlotKey` is its alias). `find()` filters one slot by environment; `empty()` and `freeze()` build one. `InversionMapper` swaps in a whole new catalog per batch, so readers never lock and never see half a batch. | Hidden | — | Minor: the copy-on-write snapshot pattern. |
| `port_binding.py` | `PortBinding` | Passive | Frozen snapshot of one port: its `selected` adapter for an environment (or `None`) and all its `adapters`. Built by `InversionMapper.bindings()` as the single source behind `describe()`, which returns a string, so the type itself never reaches users. | Hidden | — | — |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Exceptions: `domain/errors.py`

All are Public and Passive: users catch them. `IdunnError` is the shared base, so one `except`
covers the family.

| Class | Raised when |
|-------|-------------|
| `IdunnError` | Base for every Idunn error. |
| `InvalidPortError` | `@Port` is applied to anything but a Protocol (`Port(5)` included), an adapter names an unmarked port, or a non-port is resolved (for example through an explicit `@Invert` map). |
| `InvalidAdapterError` | `@Adapter` is applied to a non-class or twice to one class, two adapters share a port and key in overlapping environments (the batch that hits it registers nothing), or a built instance does not satisfy its port. |
| `AdapterNotFoundError` | No active adapter is registered for a requested port and the parameter is not optional. |
| `DiscoveryError` | A module below the discovery root fails to import and `strict=True`, or, whatever `strict` says, the root has a `__path__` entry that is not a directory (a zip). The root's own import errors propagate unwrapped. |
| `MissingTypeHintError` | An adapter constructor parameter without a default has no annotation, or one that is not a port. |
| `InjectionCycleError` | Constructor dependency resolution loops back on an adapter already under construction. |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Engine and orchestration

| File | Class | Nature | Purpose | Audience | Splittable? | Generic utility? |
|------|-------|--------|---------|----------|-------------|------------------|
| `app/idunn.py` | `Idunn` | Active | Thin **facade** and process-wide singleton (`metaclass=MetaSingleton`); `Idunn()` takes no arguments, so the environment is chosen by `IDUNN_ENV` or `reset(environment=...)`. Public surface is `autodiscover()`, `bootstrap()` (a once-per-root `autodiscover` for library entry points, delegated to `BootstrapGate`), `reset()`, `describe()` and the read-only `environment` property; owns one `InversionMapper`, one `InversionResolver` and one `BootstrapGate` and delegates. `@Invert` reaches resolution via the private `_inject` / `_has`. No public `resolve`/`register_*`, by design. | Public | — | — |
| `internal/inversion_mapper.py` | `InversionMapper` | Active | Owns the `Catalog`. Writes go through `register_batch` (ports, then adapters) under one write lock: copy once, skip what is already registered, validate each new adapter against its slot, swap once, so a batch lands whole or not at all; `register_port`/`register_adapter` are batches of one. Reads (`find`, `select`, `bindings`, and the `catalog`/`ports` properties the tests use) take one snapshot and never lock, and `bindings()` emits the `PortBinding`s behind `describe()`. | Hidden | — | — |
| `internal/inversion_resolver.py` | `InversionResolver` | Active | The construction engine: recursive constructor-time resolution, the in-progress cycle stack, and the `SINGLETON` instance cache. Asks `InversionMapper` for selections, resolves adapter-to-adapter dependencies unkeyed, and honors optional (`Port \| None` or defaulted) constructor params via `DecoratorSupport.port_from_annotation`. | Hidden | — | — |
| `internal/inversion_validator.py` | `InversionValidator` | Active (stateless) | Stateless checks: adapter-class validity (a backstop for declarations attached without `@Adapter`), duplicates within one `(port, key)` slot in overlapping envs (checked against that slot only, so validation stays linear), and instance-satisfies-port. Called by the mapper and resolver; raises `IdunnError`s. Not re-exported from `idunn.internal`. | Hidden | — | — |
| `internal/auto_discovery.py` | `AutoDiscovery` | Active | Imports every module under a dotted root name (skipping `__main__`, non-identifier parts, test modules and `exclude` patterns; the running `__main__` is reused), then registers the decorated classes into an `InversionMapper` as one all-or-nothing batch, ports first, and returns a `ReportMap`. A root whose `__path__` is not a directory (a zip) raises `DiscoveryError` whatever `strict` says; root import errors are not wrapped. Reached via `Idunn().autodiscover`. | Hidden | — | Yes: the module-scan helpers (`_module_names`, `_path_entries`, `_relative_parts`, `_is_excluded`, `_load`) are a reusable "find and import dotted modules under a package" utility. |
| `internal/bootstrap_gate.py` | `BootstrapGate` | Active (process-wide state) | Runs `bootstrap`'s discovery once per root and caches the report. Its `Lock` guards bookkeeping only, never an import. Entry-point callers that find a flight in progress wait on its `Event` and share one report; a thread that already has a run aboard (re-entry) and any thread with an import on its stack (`ImportContext`) join the flight and discover themselves instead, so nobody waits while possibly holding an import lock, or on itself. The last run out caches the `ReportMerger` merge; if the owner failed it caches nothing and carries the successful runs' reports into the retry's flight instead. `clear()` swaps the reports, flights and carried runs as one tuple, and each run captures it once at entry. Reached via `Idunn().bootstrap` and `reset()`. | Hidden | — | Minor: a once-per-key, import-safe guard, but the merge ties it to `ReportMap`. |
| `internal/bootstrap_flight.py` | `BootstrapFlight` | Passive (frozen record) | One root's first bootstrap while runs are still in progress: `runners` (one thread ident per run in progress, so nested re-entries repeat and `aboard_here()` asks "does this thread have a run in flight?"), the `done` event, finished reports (starting from any a failed flight carried) and a failed flag. Replaced copy-on-write under the gate's lock. Not re-exported from `idunn.internal`. | Hidden | — | — |
| `internal/report_merger.py` | `ReportMerger` | Active (stateless) | Merges the runs of one root's first bootstrap: sorted union of `imported_modules`, `skipped_modules` minus anything another run imported, `registered_*` concatenated in run-finish order (exact, because each class is new for exactly one atomic batch). Not re-exported from `idunn.internal`. | Hidden | — | — |
| `internal/decorator_support.py` | `DecoratorSupport` | Active | Helpers shared by the decorators and the resolver: `extract_port_parameters()` (split type hints into ports and optional names for `@Invert`), `normalize_envs()` (collapse `envs` into a normalized `frozenset`, or `None`) and `port_from_annotation()` (resolve an annotation to `(port, optional)`, unwrapping `Port \| None`). | Hidden | — | Minor: tied to Idunn rules. |
| `internal/port_registry.py` | `PortRegistry` | Active (process-wide state) | `WeakSet` of the Protocols decorated with `@Port`: `mark()` records one, `is_port()` checks exact class identity. Replaces a marker attribute, which Python 3.11 would count as a protocol member and so break structural adapters. Subclasses of a port are not ports. | Hidden | — | — |
| `util/environment.py` | `Environment` | Active (value + logic) | Frozen value object holding a resolved env `name`, plus `current()` (resolve from argument, then `IDUNN_ENV`, then `local`) and `normalize()` (strip, lowercase, `_` to `-`, blank to `local`, then validate). Reached at `Idunn()` construction, on `reset()`, and when `@Adapter(envs=...)` is normalized. | Hidden | — | Yes: `normalize()` is a generic slug normalizer. |
| `util/import_context.py` | `ImportContext` | Active (stateless) | `active()` walks the current thread's frames for `<frozen importlib._bootstrap>`, which is on the stack whenever `importlib` holds a module lock, loaders' `exec_module` and C-extension init included (a stray match only costs a spare discovery). No frame support means `True`, the safe answer. Used by `BootstrapGate` to decide who must never wait. | Hidden | — | Yes: "am I inside an import?" is project-agnostic. |
| `util/meta_singleton.py` | `MetaSingleton` | Active | Metaclass that caches one instance per class, making `Idunn()` a process-wide singleton. `__call__` takes no arguments, because a singleton can only honor them once. | Hidden | — | Yes: a generic singleton metaclass. |
| `util/qualified_name.py` | `QualifiedName` | Active | Stateless `module.QualName` renderer for any object (`repr` for anything without a qualified name, and for parameterized aliases), used by every error message, discovery reports, `describe()` and binding sort order. | Hidden | — | Yes: a generic one-liner, small enough to forget it exists. |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Examples: `examples/`

Teaching code: Public as *documentation*, but not part of the importable library. `examples/my_app`
is the README's `my_app` layout as a **discoverable package**, run from the repo root with
`poetry run python -m examples.my_app.main`. It shows the real workflow:
`Idunn().autodiscover('examples.my_app')` under `main.py`'s `if __name__ == '__main__':` guard, then
`@Invert()`-root construction, with imports only from `idunn`.

| File | Class | Nature | Purpose |
|------|-------|--------|---------|
| `my_app/ports.py` | `AppleBasketPort` | Passive | `@Port` Protocol: a contract with a single `take_apple()` method. |
| `my_app/adapters.py` | `GoldenAppleBasketAdapter` | Active | Unkeyed `@Adapter` (singleton) for `AppleBasketPort`; answers a plain `@Invert()`. |
| `my_app/main.py` | `Feast` | Active | Plain `@Invert()` root; its `AppleBasketPort` is injected and assigned to `self.basket` automatically, and `host` is passed by keyword. |

---

![Idunn](https://github.com/terracoil/idunn/raw/master/docs/images/idunn-apple-square-50.png)

## Reading the catalog

- **The public surface is tight.** Top-level `idunn` exports only the three decorators, `Idunn`,
  `LifecycleEnum`, the `ReportMap` TypedDict, and the exception hierarchy. Nothing is Mixed: the
  engine-facing domain types (`AdapterDeclaration`, `AdapterMetadata`, `Catalog`, `PortBinding`)
  never reach users, because the facade returns strings and reports rather than engine types.
- **Candidates for promotion.** `PortBinding` is the obvious one. It is a read-only snapshot that
  could become a public introspection type if `describe()` ever grows a structured sibling. Until
  someone asks, it stays a string.
- **Reusable bits worth extracting.** `MetaSingleton`, `Environment.normalize` (slug normalizer),
  `QualifiedName`, and `AutoDiscovery`'s module-scan helpers are the most project-agnostic code in
  the package.
- **Genuinely hidden classes.** The engine trio (`InversionMapper`, `InversionResolver`,
  `InversionValidator`), plus `AutoDiscovery`, `DecoratorSupport`, `PortRegistry`, `MetaSingleton`,
  `Environment` and `QualifiedName`, are never meant to be imported by end users. They sit behind
  the `Idunn` facade, which is where they are happiest.
