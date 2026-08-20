from logic import Expr, to_cnf, conjuncts
from inference import entails, relevant_clauses

class PropKB:
    def __init__(self):
        self.clauses = []
        self.history = []
        # Clauses told with background=True (the grid's static physics
        # axioms) are tracked separately so the resolution engine can apply
        # a Set-of-Support restriction — see inference.pl_resolution.
        self.background_clauses = set()

    def tell(self, sentence, background=False):
        """Add a propositional sentence to the Knowledge Base.

        background=True marks the sentence as a static world axiom (e.g. the
        grid's Safe<=>~Hazard&~Radiation&~Obstacle definitions) rather than a
        dynamic percept/derived fact. This has no effect on DPLL model
        checking; it only lets the resolution engine skip ever combining two
        pure axioms together, which is what keeps resolution queries fast on
        a fully-explored grid (see pl_resolution's docstring).
        """
        # Convert to CNF and extract clauses
        cnf_sentence = to_cnf(sentence)

        added_new = False
        for clause in conjuncts(cnf_sentence):
            if clause not in self.clauses:
                self.clauses.append(clause)
                added_new = True
            if background:
                self.background_clauses.add(clause)

        if added_new:
            self.history.append(sentence)

    def ask(self, query, method="dpll", budget=None):
        """Ask if the query is entailed by the Knowledge Base.
        method can be 'dpll' or 'resolution'.

        Before invoking the (worst-case exponential) inference engines, the
        clause set is pruned to only clauses connected to the query's symbols
        (see inference.relevant_clauses) — a sound reduction that keeps
        queries fast even as the KB grows to cover an entire grid, without
        changing the entailment answer.

        `budget` optionally overrides the engine's default search budget for
        this call (see inference.entails) — pass a small value for
        cosmetic/diagnostic queries that shouldn't be allowed to spend the
        full budget on a hard, ambiguous question.
        """
        clauses = relevant_clauses(self.clauses, query)

        if not clauses:
            kb = Expr('T')
        elif len(clauses) == 1:
            kb = clauses[0]
        else:
            kb = Expr('&', *clauses)

        if method == "resolution":
            bg = {c for c in clauses if c in self.background_clauses}
            return entails(kb, query, method=method, background=bg, budget=budget)
        return entails(kb, query, method=method, budget=budget)

    def get_clauses(self):
        """Return the current set of CNF clauses."""
        return self.clauses

    def get_history(self):
        """Return the history of told sentences."""
        return self.history
