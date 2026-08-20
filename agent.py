from logic import Symbol, Expr, equiv
from knowledge_base import PropKB
from collections import deque

# Search budget for the cosmetic "which exact neighbor is the hazard" log
# queries — see the comment where this is used in step().
DIAGNOSTIC_BUDGET = 1500

# Search budget for compare_methods(). Every per-move safety check in step()
# uses the tight, latency-conscious default budget (inference.py's
# DEFAULT_DPLL_NODE_BUDGET / DEFAULT_RESOLUTION_STEP_BUDGET) because it runs
# many times per step, every step, unattended. compare_methods() is the
# opposite: it's an explicit, occasional, user-toggled cross-validation
# ("Both" mode), so it's worth spending much more search effort to get a
# real answer from both engines rather than have an early budget cutoff on
# just one of them get mislabeled as the two engines "disagreeing" — a
# resource limit isn't a logical disagreement, and showing it as one would
# undermine the very thing this mode exists to demonstrate.
COMPARE_BUDGET = 400000

class KBAgent:
    def __init__(self, env, inference_method="dpll"):
        self.env = env
        self.kb = PropKB()
        self.visited = set()
        self.safe_unvisited = set()
        self.x, self.y = env.start_pos
        self.inference_method = inference_method
        self.t = 0
        self.path = [(self.x, self.y)]
        self.metrics = {
            "steps": 0,
            "path_cost": 0,
            "hazards_avoided": 0,
            "radiation_avoided": 0,
            "obstacles_avoided": 0,
            "kb_updates": 0,
            "inferences": 0,
            "kb_size_history": []  # clause count sampled after every KB update
        }

        self.initialize_background_knowledge()
        self.metrics["kb_size_history"].append(len(self.kb.get_clauses()))

    def set_inference_method(self, method):
        """Switch the entailment engine used for future ASK queries.

        method: 'dpll' (model checking) or 'resolution' (theorem proving).
        Safe to call between steps; does not invalidate the existing KB.
        """
        if method not in ("dpll", "resolution"):
            raise ValueError(f"Unknown inference method: {method}")
        self.inference_method = method

    def compare_methods(self, query):
        """Ask the same query via both DPLL and Resolution and return both
        results, so callers (e.g. the GUI's 'Both' mode) can display a live
        cross-validation of the two entailment procedures.

        Returns (dpll_result: bool, resolution_result: bool, agree: bool).
        """
        self.metrics["inferences"] += 2
        dpll_result = self.kb.ask(query, method="dpll", budget=COMPARE_BUDGET)
        resolution_result = self.kb.ask(query, method="resolution", budget=COMPARE_BUDGET)
        return dpll_result, resolution_result, dpll_result == resolution_result
        
    def _S(self, x, y): return Symbol(f"S_{x}_{y}")
    def _H(self, x, y): return Symbol(f"H_{x}_{y}")
    def _R(self, x, y): return Symbol(f"R_{x}_{y}")
    def _O(self, x, y): return Symbol(f"O_{x}_{y}")
    def _HS(self, x, y): return Symbol(f"HS_{x}_{y}")
    def _RS(self, x, y): return Symbol(f"RS_{x}_{y}")
    def _OS(self, x, y): return Symbol(f"OS_{x}_{y}")
    def _M(self, x, y): return Symbol(f"Move_{x}_{y}")
    
    def initialize_background_knowledge(self):
        # All of these are static "physics of the world" axioms (true for
        # every grid regardless of where hazards happen to be), so they're
        # told with background=True. This lets the resolution engine treat
        # them as a Set-of-Support "usable" pool (see knowledge_base.py /
        # inference.pl_resolution) instead of ever combining two of them
        # together, which is what keeps resolution queries fast once the KB
        # covers a whole grid's worth of these axioms.
        w, h = self.env.width, self.env.height
        for x in range(w):
            for y in range(h):
                # Safe means no hazard, no radiation, no obstacle
                self.kb.tell(equiv(self._S(x,y), Expr('&', ~self._H(x,y), ~self._R(x,y), ~self._O(x,y))), background=True)

                # Signals mean adjacent things
                adj_h = []
                adj_r = []
                adj_o = []
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        adj_h.append(self._H(nx, ny))
                        adj_r.append(self._R(nx, ny))
                        adj_o.append(self._O(nx, ny))

                if adj_h: self.kb.tell(equiv(self._HS(x,y), Expr('|', *adj_h)), background=True)
                else: self.kb.tell(~self._HS(x,y), background=True)

                if adj_r: self.kb.tell(equiv(self._RS(x,y), Expr('|', *adj_r)), background=True)
                else: self.kb.tell(~self._RS(x,y), background=True)

                if adj_o: self.kb.tell(equiv(self._OS(x,y), Expr('|', *adj_o)), background=True)
                else: self.kb.tell(~self._OS(x,y), background=True)

    def make_percept_sentence(self, percept, x, y):
        sentences = []
        if percept['HazardSignal']:
            sentences.append(self._HS(x, y))
            sentences.append(Expr('>>', Symbol('PerceiveHazardSignal'), ~Symbol('MoveForward')))
            sentences.append(Symbol('PerceiveHazardSignal'))
        else:
            sentences.append(~self._HS(x, y))
            
        if percept['RadiationSignal']:
            sentences.append(self._RS(x, y))
        else:
            sentences.append(~self._RS(x, y))

        if percept['ObstacleSignal']:
            sentences.append(self._OS(x, y))
        else:
            sentences.append(~self._OS(x, y))
            
        if percept['Safe']:
            sentences.append(self._S(x, y))
            
        return Expr('&', *sentences) if sentences else Expr('T')
        
    def get_unvisited_neighbors(self, x, y):
        neighbors = []
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if self.env.is_in_bounds(nx, ny) and (nx, ny) not in self.visited:
                neighbors.append((nx, ny))
        return neighbors

    def bfs_nearest_safe(self):
        """Find the nearest safe unvisited cell using BFS."""
        if not self.safe_unvisited:
            return None
            
        queue = deque([(self.x, self.y, [])])
        visited_bfs = {(self.x, self.y)}
        
        while queue:
            cx, cy, path = queue.popleft()
            
            if (cx, cy) in self.safe_unvisited:
                return (cx, cy)
                
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = cx + dx, cy + dy
                if self.env.is_in_bounds(nx, ny) and (nx, ny) not in visited_bfs:
                    if (nx, ny) in self.visited or (nx, ny) in self.safe_unvisited:
                        visited_bfs.add((nx, ny))
                        queue.append((nx, ny, path + [(nx, ny)]))
        
        # Fallback if disconnected (shouldn't happen in a fully explored connected grid)
        return list(self.safe_unvisited)[0]

    def step(self):
        """Perform one step of the KB Agent loop. Returns (target, eval_results, percept, derivation)."""
        # 1. TELL the KB what we perceive
        percept = self.env.get_percepts(self.x, self.y)
        percept_sentence = self.make_percept_sentence(percept, self.x, self.y)
        prev_clauses_count = len(self.kb.get_clauses())
        self.kb.tell(percept_sentence)
        self.visited.add((self.x, self.y))
        
        self.metrics["kb_updates"] += (len(self.kb.get_clauses()) - prev_clauses_count)
        self.metrics["kb_size_history"].append(len(self.kb.get_clauses()))
        
        # 2. ASK KB about adjacent unvisited cells (UP, DOWN, LEFT, RIGHT)
        eval_results = {}
        derivation = []
        
        direction_map = {
            (0, -1): "UP",
            (0, 1): "DOWN",
            (-1, 0): "LEFT",
            (1, 0): "RIGHT"
        }
        
        for dx, dy in direction_map.keys():
            nx, ny = self.x + dx, self.y + dy
            direction = direction_map[(dx, dy)]
            
            if not self.env.is_in_bounds(nx, ny):
                continue
                
            if (nx, ny) in self.visited:
                eval_results[direction] = "VISITED"
                continue
                
            if (nx, ny) in self.safe_unvisited:
                eval_results[direction] = "ALLOWED"
                continue
                
            # Ask if it is safe
            self.metrics["inferences"] += 1
            is_safe = self.kb.ask(self._S(nx, ny), method=self.inference_method)
            
            # Ask if it's explicitly unsafe
            self.metrics["inferences"] += 1
            is_unsafe = self.kb.ask(~self._S(nx, ny), method=self.inference_method)
            
            if is_safe:
                self.safe_unvisited.add((nx, ny))
                eval_results[direction] = "ALLOWED"
            elif is_unsafe:
                eval_results[direction] = "UNSAFE"
                
                # Check why it's unsafe for the derivation log. This asks "is
                # THIS SPECIFIC neighbor the hazard" out of possibly several
                # ambiguous candidates behind one shared signal — logically
                # the hardest kind of query this KB can pose (a non-Horn
                # disjunction), and purely cosmetic (it only decorates the
                # log line; the safety decision itself was already made
                # above from is_unsafe). So it runs on a small budget: a
                # quick, cheap attempt, falling back to the generic message
                # rather than spending the full search budget on it.
                self.metrics["inferences"] += 3
                if self.kb.ask(self._H(nx, ny), method=self.inference_method, budget=DIAGNOSTIC_BUDGET):
                    derivation.append(f"Hazard_{nx}_{ny} -> NOT Safe_{nx}_{ny} -> NOT Move_{nx}_{ny}")
                    self.metrics["hazards_avoided"] += 1
                elif self.kb.ask(self._R(nx, ny), method=self.inference_method, budget=DIAGNOSTIC_BUDGET):
                    derivation.append(f"Radiation_{nx}_{ny} -> NOT Safe_{nx}_{ny} -> NOT Move_{nx}_{ny}")
                    self.metrics["radiation_avoided"] += 1
                elif self.kb.ask(self._O(nx, ny), method=self.inference_method, budget=DIAGNOSTIC_BUDGET):
                    derivation.append(f"Obstacle_{nx}_{ny} -> NOT Safe_{nx}_{ny} -> NOT Move_{nx}_{ny}")
                    self.metrics["obstacles_avoided"] += 1
                else:
                    derivation.append(f"NOT Safe_{nx}_{ny} -> NOT Move_{nx}_{ny}")
            else:
                eval_results[direction] = "UNKNOWN"
                    
        # 3. Choose action
        action_target = None
        action_direction = None
        
        for dx, dy in direction_map.keys():
            nx, ny = self.x + dx, self.y + dy
            if (nx, ny) in self.safe_unvisited:
                action_target = (nx, ny)
                action_direction = direction_map[(dx, dy)]
                break
                
        if not action_target and self.safe_unvisited:
            action_target = self.bfs_nearest_safe()
            action_direction = "JUMP (REPLANNING)"
            
        if action_target:
            self.safe_unvisited.remove(action_target)
            self.x, self.y = action_target
            self.path.append((self.x, self.y))
            self.t += 1
            self.metrics["steps"] += 1
            self.metrics["path_cost"] += 1
            return action_target, eval_results, percept, derivation, action_direction
            
        return None, eval_results, percept, derivation, "NONE"
