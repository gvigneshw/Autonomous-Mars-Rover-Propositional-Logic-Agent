"""Integration tests for agent.py — the KB-agent perception/inference/action loop."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from environment import Environment
from agent import KBAgent


class TestKBAgentIntegration(unittest.TestCase):
    def _fixed_env(self):
        """A small, deterministic 4x4 grid with hand-placed hazards/radiation/
        obstacles (no randomness) so the test is fully reproducible."""
        env = Environment(width=4, height=4)
        env.add_hazard(2, 0)
        env.add_radiation(0, 2)
        env.add_obstacle(3, 1)
        return env

    def test_agent_never_steps_onto_a_known_danger_cell(self):
        env = self._fixed_env()
        agent = KBAgent(env, inference_method="dpll")

        for _ in range(50):
            target, eval_results, percept, derivation, action_dir = agent.step()
            self.assertNotIn((agent.x, agent.y), env.hazards)
            self.assertNotIn((agent.x, agent.y), env.radiations)
            self.assertNotIn((agent.x, agent.y), env.obstacles)
            if not target and action_dir == "NONE":
                break
            if (agent.x, agent.y) == env.goal_pos:
                break

    def test_kb_grows_monotonically(self):
        env = self._fixed_env()
        agent = KBAgent(env, inference_method="dpll")
        sizes = [len(agent.kb.get_clauses())]
        for _ in range(10):
            agent.step()
            sizes.append(len(agent.kb.get_clauses()))
        # KB clause count must never shrink
        for i in range(1, len(sizes)):
            self.assertGreaterEqual(sizes[i], sizes[i - 1])

    def test_set_inference_method_and_compare(self):
        env = self._fixed_env()
        agent = KBAgent(env, inference_method="dpll")
        agent.step()

        agent.set_inference_method("resolution")
        self.assertEqual(agent.inference_method, "resolution")
        with self.assertRaises(ValueError):
            agent.set_inference_method("bogus")

        from logic import Symbol
        dpll_r, res_r, agree = agent.compare_methods(Symbol(f"S_{agent.x}_{agent.y}"))
        self.assertIsInstance(dpll_r, bool)
        self.assertIsInstance(res_r, bool)
        self.assertTrue(agree)

    def test_kb_size_history_tracked(self):
        env = self._fixed_env()
        agent = KBAgent(env, inference_method="dpll")
        self.assertEqual(len(agent.metrics["kb_size_history"]), 1)
        agent.step()
        self.assertEqual(len(agent.metrics["kb_size_history"]), 2)

    def test_full_size_grid_stays_interactive(self):
        """Regression guard: on the hackathon's default 8x8 grid, a batch of
        steps (each doing several DPLL + a resolution query) must stay fast
        enough for a live game loop. This is exactly the scenario that used
        to hang for 80+ seconds before the inference-engine performance work
        (relevance filtering, Set-of-Support resolution, a single-pass
        find_pure_symbol, and search budgets) — so a generous wall-clock
        ceiling here catches a real regression, not just a slow machine.
        """
        import time
        env = Environment(width=8, height=8)
        env.generate_random_env(num_hazards=8, num_radiations=6, num_obstacles=4)
        agent = KBAgent(env, inference_method="dpll")

        t0 = time.time()
        for _ in range(12):
            agent.step()
        elapsed = time.time() - t0
        self.assertLess(elapsed, 15.0, f"12 steps on an 8x8 grid took {elapsed:.1f}s — too slow for live play")

        # A resolution-mode query on the same grown KB must also stay fast.
        from logic import Symbol
        agent.set_inference_method("resolution")
        q = Symbol(f"S_{agent.x}_{agent.y}")
        t0 = time.time()
        agent.kb.ask(q, method="resolution")
        self.assertLess(time.time() - t0, 5.0, "a single resolution query took too long")

    def test_compare_methods_does_not_false_disagree_on_full_size_grid(self):
        """Regression guard: compare_methods() must use a generous enough
        search budget that it never reports a DPLL/Resolution disagreement
        that's actually just one engine's budget running out — a handful of
        8x8-grid runs used to do exactly that (see agent.py's COMPARE_BUDGET
        comment) and would otherwise make the GUI's 'Both' mode look like it
        found a real logical inconsistency between the two engines."""
        from logic import Symbol
        for seed in range(3):
            env = Environment(width=8, height=8)
            env.generate_random_env(num_hazards=6, num_radiations=5, num_obstacles=3)
            agent = KBAgent(env, inference_method="dpll")
            for _ in range(3):
                target, eval_results, percept, derivation, action_dir = agent.step()
                if action_dir == "NONE":
                    break
                q = Symbol(f"S_{agent.x}_{agent.y}")
                dpll_r, res_r, agree = agent.compare_methods(q)
                self.assertTrue(agree, f"seed={seed}: DPLL={dpll_r} Resolution={res_r} disagreed")


if __name__ == "__main__":
    unittest.main()
