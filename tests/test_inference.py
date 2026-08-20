"""Unit tests for inference.py — resolution theorem proving and DPLL model checking."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logic import Symbol, Expr, to_cnf, conjuncts
from inference import (
    pl_resolve, pl_resolution, dpll_satisfiable, tt_entails, entails,
)


class TestPLResolve(unittest.TestCase):
    def test_resolves_complementary_literals(self):
        a, b, c = Symbol("A"), Symbol("B"), Symbol("C")
        # (A | B) and (~A | C) resolve to (B | C)
        ci = Expr('|', a, b)
        cj = Expr('|', ~a, c)
        resolvents = pl_resolve(ci, cj)
        self.assertEqual(len(resolvents), 1)
        self.assertIn(resolvents[0].op, ('|',))
        self.assertEqual(set(resolvents[0].args), {b, c})

    def test_produces_empty_clause_on_direct_contradiction(self):
        a = Symbol("A")
        resolvents = pl_resolve(a, ~a)
        self.assertIn(Expr('F'), resolvents)

    def test_tautology_is_eliminated(self):
        a, b = Symbol("A"), Symbol("B")
        # (A | B) and (~A | ~B) resolve on A -> (B | ~B), a tautology, must be dropped
        ci = Expr('|', a, b)
        cj = Expr('|', ~a, ~b)
        resolvents = pl_resolve(ci, cj)
        # Only the non-tautological resolvent (on B) should survive
        for r in resolvents:
            lits = r.args if r.op == '|' else (r,)
            for lit in lits:
                self.assertNotIn(~lit, lits)

    def test_factoring_removes_duplicate_literals(self):
        a, b = Symbol("A"), Symbol("B")
        # (A | B | A) and (~A) resolve; result should not contain duplicate B's
        ci = Expr('|', a, b, a)
        cj = ~a
        resolvents = pl_resolve(ci, cj)
        self.assertEqual(len(resolvents), 1)
        self.assertEqual(resolvents[0], b)


class TestPLResolution(unittest.TestCase):
    def test_modus_ponens_entailment(self):
        a, b = Symbol("A"), Symbol("B")
        kb = Expr('&', a, a >> b)
        self.assertTrue(pl_resolution(kb, b))

    def test_non_entailment(self):
        a, b, c = Symbol("A"), Symbol("B"), Symbol("C")
        kb = Expr('&', a, a >> b)
        self.assertFalse(pl_resolution(kb, c))

    def test_contradictory_kb_entails_anything(self):
        a, b = Symbol("A"), Symbol("B")
        kb = Expr('&', a, ~a)
        self.assertTrue(pl_resolution(kb, b))


class TestDPLL(unittest.TestCase):
    def test_satisfiable_sentence(self):
        a, b = Symbol("A"), Symbol("B")
        self.assertTrue(dpll_satisfiable(a | b))

    def test_unsatisfiable_sentence(self):
        a = Symbol("A")
        self.assertFalse(dpll_satisfiable(Expr('&', a, ~a)))

    def test_tt_entails_matches_modus_ponens(self):
        a, b = Symbol("A"), Symbol("B")
        kb = Expr('&', a, a >> b)
        self.assertTrue(tt_entails(kb, b))
        c = Symbol("C")
        self.assertFalse(tt_entails(kb, c))


class TestCrossValidation(unittest.TestCase):
    """Resolution and DPLL model checking must agree on entailment — this is
    the property the GUI's 'Both' inference mode relies on to demonstrate
    both engines live."""

    def test_resolution_and_dpll_agree(self):
        a, b, c = Symbol("A"), Symbol("B"), Symbol("C")
        cases = [
            (Expr('&', a, a >> b), b, True),
            (Expr('&', a, a >> b), c, False),
            (Expr('&', a | b, ~a), b, True),
            (Expr('&', a, ~a), c, True),   # contradictory KB entails everything
            (a, b, False),
        ]
        for kb, query, expected in cases:
            dpll_result = entails(kb, query, method="dpll")
            res_result = entails(kb, query, method="resolution")
            self.assertEqual(dpll_result, expected)
            self.assertEqual(res_result, expected)
            self.assertEqual(dpll_result, res_result)


if __name__ == "__main__":
    unittest.main()
