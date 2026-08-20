"""Unit tests for knowledge_base.py — the dynamic PropKB used by the rover agent."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logic import Symbol, Expr, equiv
from knowledge_base import PropKB


class TestPropKBTell(unittest.TestCase):
    def test_tell_grows_clause_list(self):
        kb = PropKB()
        self.assertEqual(kb.get_clauses(), [])
        a = Symbol("A")
        kb.tell(a)
        self.assertEqual(len(kb.get_clauses()), 1)

    def test_tell_does_not_duplicate_existing_clauses(self):
        kb = PropKB()
        a, b = Symbol("A"), Symbol("B")
        kb.tell(Expr('|', a, b))
        n = len(kb.get_clauses())
        kb.tell(Expr('|', a, b))  # telling the same sentence again
        self.assertEqual(len(kb.get_clauses()), n)

    def test_tell_splits_conjunction_into_multiple_clauses(self):
        kb = PropKB()
        a, b = Symbol("A"), Symbol("B")
        kb.tell(Expr('&', a, b))
        self.assertEqual(len(kb.get_clauses()), 2)

    def test_history_only_records_sentences_that_added_new_knowledge(self):
        kb = PropKB()
        a = Symbol("A")
        kb.tell(a)
        kb.tell(a)  # redundant, should not extend history
        self.assertEqual(len(kb.get_history()), 1)


class TestPropKBAsk(unittest.TestCase):
    def test_ask_true_for_entailed_query(self):
        kb = PropKB()
        a, b = Symbol("A"), Symbol("B")
        kb.tell(a)
        kb.tell(a >> b)
        self.assertTrue(kb.ask(b, method="dpll"))
        self.assertTrue(kb.ask(b, method="resolution"))

    def test_ask_false_for_unknown_query(self):
        kb = PropKB()
        a, c = Symbol("A"), Symbol("C")
        kb.tell(a)
        self.assertFalse(kb.ask(c, method="dpll"))
        self.assertFalse(kb.ask(c, method="resolution"))

    def test_ask_on_empty_kb(self):
        kb = PropKB()
        a = Symbol("A")
        self.assertFalse(kb.ask(a))

    def test_rover_style_safety_rule(self):
        """Mirrors the agent's real usage: Safe(x,y) <=> ~Hazard(x,y) & ~Radiation(x,y),
        then a percept telling us there IS a hazard should make Safe provably false."""
        kb = PropKB()
        safe = Symbol("S_1_1")
        hazard = Symbol("H_1_1")
        radiation = Symbol("R_1_1")
        kb.tell(equiv(safe, Expr('&', ~hazard, ~radiation)))
        kb.tell(hazard)  # percept: this cell is a hazard
        self.assertTrue(kb.ask(~safe, method="dpll"))
        self.assertFalse(kb.ask(safe, method="dpll"))

    def test_contradiction_detection(self):
        """If the KB becomes contradictory, it entails both a literal and its negation."""
        kb = PropKB()
        a = Symbol("A")
        kb.tell(a)
        kb.tell(~a)
        self.assertTrue(kb.ask(a))
        self.assertTrue(kb.ask(~a))


if __name__ == "__main__":
    unittest.main()
