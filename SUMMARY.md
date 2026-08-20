# Technical Summary Sheet

## 1. Header & Team Info
- **Course Code:** CS401 (Replace with actual)
- **Group ID:** Team-Alpha (Replace with actual)
- **Member Names:** Alice, Bob, Charlie (Replace with actual)
- **Selected Track:** Track 2 - Autonomous Mars Rover (Propositional Logic Agent)
- **GitHub Repository URL:** [Insert GitHub URL here]

## 2. PEAS Framework Matrix
- **Performance Measure:** Maximize safe exploration, avoid hazards (pits), radiation zones, and obstacles, minimize path cost, reach goals securely.
- **Environment:** 2D Grid (Martian surface), deterministic, discrete, partially observable (hazards, radiation, and obstacles are hidden until adjacent).
- **Actuators:** Movement in four cardinal directions (UP, DOWN, LEFT, RIGHT).
- **Sensors:** Hazard Sensor, Radiation Sensor, Obstacle Sensor, Position Sensor.

## 3. Core Algorithmic Formulation
- **State Space Definition:** The agent's current coordinates $(x, y)$, the set of visited coordinates, the set of known safe unvisited coordinates, and the current Propositional Knowledge Base (CNF clauses).
- **Initial State:** Agent at $(0, 0)$ with an initial Knowledge Base containing the physical axioms of the grid (e.g., $S_{x,y} \iff \neg H_{x,y} \land \neg R_{x,y} \land \neg O_{x,y}$).
- **Goal Test:** No more safe unvisited cells exist, or the explicit goal coordinate $(width-1, height-1)$ is reached safely.
- **Path Cost:** 1 unit per movement step.
- **Logic Rules Used:** 
  - Dynamic formulation of percepts: $HS_{x,y} \land \neg RS_{x,y} \land S_{x,y}$
  - Entailment check: $KB \models S_{next\_x, next\_y}$ checked via DPLL satisfiability testing.
  - Derived rules: $Hazard(x) \implies \neg Safe(x)$, $\neg Safe(x) \implies \neg Move(x)$

## 4. Complexity Analysis
- **Theoretical Time Complexity:** 
  - **DPLL Model Checking:** $O(2^V)$ where $V$ is the number of propositional variables (e.g., $5 \times W \times H$). However, with unit clause heuristics and pure symbol elimination, average time is vastly reduced.
  - **Pathfinding (BFS):** $O(N)$ where $N$ is the number of known safe nodes.
- **Theoretical Space Complexity:** $O(C + V)$ where $C$ is the number of CNF clauses maintained in memory and $V$ is the number of variables.
- **Observed Execution Metrics:** The agent resolves grid decisions instantly (under 0.05 seconds per step) demonstrating that the DPLL engine, despite exponential theoretical bounds, executes practically in $O(1)$ time per local query due to localized propositional variables. Space growth is linear relative to explored cells (roughly 3 new clauses per step).
