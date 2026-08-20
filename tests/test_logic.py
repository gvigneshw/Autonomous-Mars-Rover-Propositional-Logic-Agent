"""Unit tests for logic.py — the propositional logic AST and CNF converter."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logic import Symbol, Expr, equiv, to_cnf, conjuncts, disjuncts, prop_symbols, is_symbol


class TestExpr(unittest.TestCase):
    def test_symbol_identity_and_equality(self):
        a1 = Symbol("A")
        a2 = Symbol("A")
        b = Symbol("B")
        self.assertEqual(a1, a2)
        self.assertNotEqual(a1, b)
        self.assertTrue(is_symbol(a1))

    def test_operators_build_correct_tree(self):
        a, b = Symbol("A"), Symbol("B")
        self.assertEqual((a & b), Expr('&', a, b))
        self.assertEqual((a | b), Expr('|', a, b))
        self.assertEqual((~a), Expr('~', a))
        self.assertEqual((a >> b), Expr('>>', a, b))


class TestToCNF(unittest.TestCase):
    def test_implication_becomes_disjunction(self):
        a, b = Symbol("A"), Symbol("B")
        cnf = to_cnf(a >> b)
        # A -> B  ==  ~A | B
        clauses = conjuncts(cnf)
        self.assertEqual(len(clauses), 1)
        lits = set(disjuncts(clauses[0]))
        self.assertEqual(lits, {~a, b})

    def test_biconditional_produces_two_clauses(self):
        a, b = Symbol("A"), Symbol("B")
        cnf = to_cnf(equiv(a, b))
        clauses = conjuncts(cnf)
        self.assertEqual(len(clauses), 2)
        lit_sets = [set(disjuncts(c)) for c in clauses]
        self.assertIn({~a, b}, lit_sets)
        self.assertIn({a, ~b}, lit_sets)

    def test_double_negation_eliminated(self):
        a = Symbol("A")
        cnf = to_cnf(~~a)
        self.assertEqual(cnf, a)

    def test_demorgan_negated_conjunction(self):
        a, b = Symbol("A"), Symbol("B")
        cnf = to_cnf(~(a & b))
        clauses = conjuncts(cnf)
        self.assertEqual(len(clauses), 1)
        self.assertEqual(set(disjuncts(clauses[0])), {~a, ~b})

    def test_distribution_over_nested_or(self):
        a, b, c = Symbol("A"), Symbol("B"), Symbol("C")
        # A | (B & C)  ==  (A | B) & (A | C)
        cnf = to_cnf(a | (b & c))
        clauses = conjuncts(cnf)
        self.assertEqual(len(clauses), 2)
        lit_sets = [set(disjuncts(cl)) for cl in clauses]
        self.assertIn({a, b}, lit_sets)
        self.assertIn({a, c}, lit_sets)

    def test_prop_symbols_collects_all_atoms(self):
        a, b, c = Symbol("A"), Symbol("B"), Symbol("C")
        sentence = Expr('&', a >> b, ~c)
        self.assertEqual(prop_symbols(sentence), {a, b, c})


if __name__ == "__main__":
    unittest.main()
