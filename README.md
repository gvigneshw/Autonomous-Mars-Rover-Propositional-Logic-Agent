# Autonomous Mars Rover – Propositional Logic Agent

Track 2 submission for the AIML Hackathon. A Knowledge-Based Logical Agent
navigates a 2D Martian grid containing hidden hazards and radiation zones,
using **pure Propositional Logic** — a from-scratch CNF/resolution/DPLL
engine, no external theorem-prover libraries. The Knowledge Base is updated
dynamically at every step from new percepts, and every move is only ever
taken once the KB can *prove* it safe.

## Quick start

```bash
pip install -r requirements.txt
python game.py
```

That's the flagship, full GUI experience — see below for the other two ways
to run it.

## Core features

- **Pure Propositional Logic**: hand-written logic AST and CNF conversion
  ([logic.py](logic.py)) — no `sympy`, no external SAT/theorem-prover.
- **Two independent inference engines**, switchable live:
  - **DPLL model checking** ([inference.py](inference.py)) with unit
    propagation, pure-symbol elimination, and a variable-degree branching
    heuristic.
  - **Resolution theorem proving** ([inference.py](inference.py)) with
    factoring, tautology elimination, forward subsumption, and a
    Set-of-Support strategy.
  - A **cross-validation mode** ("Both") asks the same query through both
    engines and shows they agree — a live demonstration that the two
    theoretically-equivalent procedures actually produce the same answer.
- **Dynamic Knowledge Base** ([knowledge_base.py](knowledge_base.py)):
  grows every step from percepts, is queried with `ask(query, method=...)`,
  and is fully inspectable (`K` dumps every clause currently held).
- **Explicit derivation logging**: `Hazard(x,y) → ¬Safe(x,y) → ¬Move(x,y)`
  chains are printed for every rejected neighbor.
- **Three front-ends**, same underlying agent/logic engine:
  1. **`game.py`** — a full Pygame GUI (recommended, see below).
  2. **`gui.py`** — a lightweight Tkinter GUI (zero extra installs).
  3. **`main.py`** — pure terminal, richly formatted live log.

## Option 1: `game.py` — the full GUI game (recommended)

```bash
pip install pygame
python game.py
```

Run this **from a normal terminal window**, and keep that terminal visible
next to the game window. `game.py` never redirects `stdout` — every step
prints the full, professional KB log (percept, new CNF clauses added,
neighbor-by-neighbor inference results, the derivation chain for any
rejected move, and the chosen action) straight to that terminal in real
time. That terminal + the game window *is* the required split-screen shot
for the submission video.

Everything on screen is drawn procedurally (pygame primitives only — no
image files are bundled or downloaded):

- **Fog of war** — unexplored cells are dark and marked `?`. A cell lights
  up two different ways: pale green the moment the KB can *prove* it safe
  (before the rover ever sets a wheel on it), and full green with a
  checkmark once actually visited.
- **Live "scan" rings** — every step, each evaluated neighbor gets a
  brief color-coded ring: green = provably safe, red = provably unsafe,
  gray = the KB genuinely doesn't know yet. This is the direct visual of
  `ASK(KB, Safe(x,y))` happening.
- **Hazard / radiation / obstacle icons** — a warning triangle, a
  pulsing radiation trefoil, and a rock cluster, revealed only once the KB
  has actually proven that cell dangerous (never before — no cheating by
  peeking at ground truth).
- **A tweened, glowing rover** with a fading thruster trail and a heading
  indicator, instead of instantly teleporting between cells.
- **A live HUD**: step counter, mission stats, a KB-size sparkline (watch
  the knowledge base grow in real time), the most recent inference result,
  and a compact mission-log ticker.
- **A mission-complete overlay** with final metrics (SUCCESS or BLOCKED —
  see "On 'BLOCKED' runs" below).

### Controls

| Action | Key | Button |
|---|---|---|
| Single step | `Space` | STEP |
| Auto-run / pause | `A` | AUTO RUN |
| Cycle inference mode (DPLL → Resolution → Both) | `M` | MODE |
| Restart with a fresh environment | `R` | RESTART |
| Speed down / up | `-` / `+` | `-` / `+` |
| Dump the **entire** current KB to the terminal | `K` | — |
| Quit | `Esc` / `Q` | — |

### On "BLOCKED" runs

`game.py` regenerates the environment (never changing `environment.py`'s
own random-generation logic, just resampling it) until a safe path to the
goal *exists in ground truth* — so the mission is always physically
solvable. Even so, you'll sometimes see **MISSION BLOCKED** instead of
SUCCESS: the rover's hazard/radiation/obstacle *signals* are deliberately
ambiguous (a signal at `(x,y)` only means "one of up to four neighbors is
dangerous", not which one — the same style of underconstrained sensing as
the classic Wumpus World). The agent never guesses; if the KB can't
*prove* a neighbor safe yet, it won't move there, even if a path exists
that it simply hasn't gathered enough evidence for. That's the intended
behavior of a sound logical agent, not a bug — and it's a good moment to
point out on camera.

## Option 2: `gui.py` — lightweight Tkinter GUI

No extra installs (Tkinter ships with Python):

```bash
python gui.py
```

Click **STEP** / **AUTO RUN** / **RESTART**. Note: this front-end redirects
its own log into an in-window text box rather than the real terminal, so it
does *not* by itself satisfy the split-screen requirement — use `game.py`
for the recording.

## Option 3: `main.py` — pure terminal

```bash
python main.py
```

Auto-runs to completion, printing the same rich per-step log block
directly to the terminal (no GUI window at all — pair it with a live ASCII
map, which it also prints after every step).

## Running the tests

```bash
python -m unittest discover tests -v
```

33 unit/integration tests cover:

- `logic.py`'s CNF conversion (implication elimination, De Morgan, `AND`
  distribution over `OR`).
- `inference.py`'s resolution engine (factoring, tautology elimination,
  contradiction detection) and DPLL model checking (satisfiable /
  unsatisfiable cases), plus a cross-validation suite asserting the two
  engines agree on every case.
- `knowledge_base.py`'s `tell`/`ask` semantics (no duplicate clauses,
  contradiction handling).
- `agent.py` end-to-end: the rover never steps onto a hazard/radiation/
  obstacle cell, the KB only ever grows, and — as a regression guard for
  the performance work described below — a batch of steps on the
  hackathon's default 8x8 grid stays fast enough for live play.

## Architecture & modules

- **`logic.py`** — the propositional logic AST (`Expr`) and `to_cnf`.
- **`inference.py`** — the inference engine: `pl_resolution` (resolution
  theorem proving) and `dpll_satisfiable`/`tt_entails` (DPLL model
  checking), plus `relevant_clauses` (a sound pruning step shared by both).
- **`knowledge_base.py`** — `PropKB`: `tell(sentence, background=...)` /
  `ask(query, method=...)`, clause history, and background-vs-dynamic
  clause tracking.
- **`environment.py`** — the 2D grid: hazards, radiation, obstacles,
  percept generation.
- **`agent.py`** — `KBAgent`: the classic `TELL → ASK → TELL` loop,
  percept-to-sentence formulation, BFS replanning over known-safe cells,
  and mission metrics.
- **`main.py`** / **`gui.py`** / **`game.py`** — the three front-ends
  described above.
- **`tests/`** — the unit/integration test suite.

## Propositional language

For every coordinate `(x, y)`:

| Symbol | Meaning |
|---|---|
| `S_x_y` | Cell `(x,y)` is Safe |
| `H_x_y` / `R_x_y` / `O_x_y` | Cell has a Hazard / Radiation / Obstacle |
| `HS_x_y` / `RS_x_y` / `OS_x_y` | A Hazard/Radiation/Obstacle **signal** was perceived at `(x,y)` (i.e. true iff *some* neighbor has it) |
| `PerceiveHazardSignal`, `MoveForward` | The example rule required by the spec |

### Background axioms (told once, marked `background=True`)

- `Safe(x,y) ⟺ ¬Hazard(x,y) ∧ ¬Radiation(x,y) ∧ ¬Obstacle(x,y)`
- `HazardSignal(x,y) ⟺ Hazard(n₁) ∨ Hazard(n₂) ∨ … ` (over in-bounds neighbors), and
  symmetrically for `RadiationSignal` / `ObstacleSignal`.

### Percept sentences (told every step)

When the rover perceives a hazard signal it also asserts the example rule
from the spec:

```
PerceiveHazardSignal ∧ (PerceiveHazardSignal ⟹ ¬MoveForward)
```

and the corresponding `HS_x_y` / `RS_x_y` / `OS_x_y` / `S_x_y` literals for
its current cell.

### Deciding a move

Before stepping onto neighbor `(nx, ny)`, the agent asks:

```
KB ⊨ Safe(nx, ny)   — via DPLL, Resolution, or both
```

Only a `YES` makes the move `ALLOWED`.

## Problem formulation & PEAS

- **State space**: rover coordinates `(x, y)`, the visited set, the set of
  KB-proven-safe unvisited cells, and the current CNF Knowledge Base.
- **Initial state**: rover at `(0, 0)`, KB containing the background axioms.
- **Goal test**: goal cell reached safely, or no provably-safe unvisited
  cell remains.
- **Path cost**: 1 per step.
- **Performance measure**: maximize safe exploration / reach the goal,
  avoid hazards, radiation and obstacles, minimize path cost.
- **Environment**: 2D grid, deterministic, discrete, partially observable
  (danger cells are hidden until their ambiguous signal is perceived).
- **Actuators**: move UP / DOWN / LEFT / RIGHT.
- **Sensors**: Hazard / Radiation / Obstacle signal, Safe, Bump.

See [SUMMARY.md](SUMMARY.md) / [SUMMARY.pdf](SUMMARY.pdf) for the full PEAS
matrix, algorithmic formulation, and complexity analysis required for the
Technical Summary Sheet.

## A note on performance (why the KB doesn't grind to a halt on a full grid)

A naive resolution loop or a DPLL search without good heuristics will
genuinely blow up on this KB once it covers a whole grid — this was
measured and fixed during development, not merely assumed:

- **`relevant_clauses`** prunes the clause set fed to either engine to only
  clauses connected (directly or transitively) to the query's symbols — a
  *sound* reduction (disconnected clauses provably can't affect the
  entailment result), not an approximation.
- **DPLL** shrinks its clause list every recursion (dropping clauses already
  satisfied by the partial model instead of re-scanning them), uses a
  single linear pass for pure-symbol elimination (the naive per-symbol scan
  was, empirically, the single biggest bottleneck — over 20s of a 22s
  profiled step), and branches by variable degree instead of arbitrary
  order.
- **Resolution** runs unit propagation first, uses a "given clause" loop so
  no pair is ever re-checked, applies forward subsumption, and — most
  importantly — a **Set-of-Support** restriction that never resolves two
  pure background axioms together (sound unconditionally; complete here
  since the background axioms alone are always satisfiable).
- Both engines accept a **search-node budget**; a query that can't be
  settled within it is reported as "not proven" — the same cautious
  default the agent already applies to any unproven query — rather than
  blocking the game loop. This is also a small, honest instance of the
  "uncertainty handling" extra-credit feature: some queries are genuinely
  hard (the KB contains real non-Horn clauses), and the agent degrades
  gracefully instead of freezing.

With all of the above, the hackathon's default 8x8 grid runs at roughly
0.2–0.3s per step end-to-end (both engines), down from an unusable 80+
seconds before this work.
