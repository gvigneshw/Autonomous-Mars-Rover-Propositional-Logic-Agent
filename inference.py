import sys
from logic import Expr, to_cnf, conjuncts, disjuncts, prop_symbols

# Branching depth is bounded by the number of propositional variables still
# unassigned, which scales with grid size (7 symbols per cell). Raise the
# recursion ceiling defensively so a large grid's DPLL search never hits
# Python's default recursion limit.
if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

# Propositional entailment is coNP-complete in general, and this KB contains
# genuinely non-Horn clauses (the "signal <=> OR(neighbor hazards)" axioms),
# so some individual queries — e.g. "is *this specific* neighbor the hazard,
# given an ambiguous signal and several untested candidates?" — can require
# real exponential search. That's fine for an offline theorem prover, but
# fatal for a live game loop that must keep queuing frames. Both engines
# below accept a search-node budget: if a query can't be settled within it,
# it is treated as "not proven" (the same cautious default the agent already
# falls back to for any query it can't establish) rather than blocking. This
# never produces an unsound "yes" — only an occasional, honest "couldn't
# prove it in time", which is itself a form of the uncertainty handling the
# rover already exposes as UNKNOWN/POSSIBLY-HAZARD cells.
DEFAULT_DPLL_NODE_BUDGET = 6000
DEFAULT_RESOLUTION_STEP_BUDGET = 60000

class InferenceBudgetExceeded(Exception):
    """Internal signal that a DPLL search exceeded its node budget."""
    pass


def relevant_clauses(clauses, query):
    """Return the subset of `clauses` that share a propositional symbol,
    directly or transitively, with `query`.

    This is a sound pruning step, not an approximation: two CNF clauses can
    only ever be resolved together if they share a complementary literal
    (same symbol, opposite sign), and every resolvent's symbol set is a
    subset of its two parents' symbol sets. So a clause whose symbols never
    connect back to the query's symbols through any chain of shared symbols
    can never take part in a resolution refutation of the query, and can
    never influence a DPLL entailment check on it either. Dropping such
    clauses before calling the (expensive, worst-case exponential) inference
    engines keeps every-step queries fast even as the background knowledge
    base grows to cover an entire grid, while leaving the entailment result
    identical to running against the full KB.
    """
    query_syms = prop_symbols(query)
    if not query_syms or not clauses:
        return list(clauses)

    clause_syms = [prop_symbols(c) for c in clauses]
    included = set()
    frontier_syms = set(query_syms)

    changed = True
    while changed:
        changed = False
        for i, syms in enumerate(clause_syms):
            if i in included:
                continue
            if syms & frontier_syms:
                included.add(i)
                new_syms = syms - frontier_syms
                if new_syms:
                    frontier_syms |= new_syms
                    changed = True

    return [clauses[i] for i in sorted(included)]

def pl_resolve(ci, cj):
    """Return all clauses that can be obtained by resolving clauses ci and cj."""
    resolvents = []
    # Factoring step: dedupe each clause's own literals first. Without this,
    # a clause like (A | B | A) would make the loop below visit the literal
    # 'A' twice and emit the same resolvent twice for a single logical match.
    di = list(dict.fromkeys(disjuncts(ci)))
    dj = list(dict.fromkeys(disjuncts(cj)))
    
    for di_elem in di:
        for dj_elem in dj:
            # Check if di_elem and dj_elem are complementary literals
            if di_elem == ~dj_elem or ~di_elem == dj_elem:
                # Resolve these two!
                res_di = [d for d in di if d != di_elem]
                res_dj = [d for d in dj if d != dj_elem]
                
                res = list(set(res_di + res_dj)) # Remove duplicates (factoring)
                
                # Check for tautology (e.g. A | ~A)
                is_tautology = False
                for r in res:
                    if ~r in res or r == ~r:
                        is_tautology = True
                        break
                
                if not is_tautology:
                    if not res:
                        resolvents.append(Expr('F')) # Empty clause, contradiction
                    elif len(res) == 1:
                        resolvents.append(res[0])
                    else:
                        res.sort() # Sort for canonical form
                        resolvents.append(Expr('|', *res))
    return resolvents

def _complement(literal):
    """Return the complementary literal (A <-> ~A)."""
    return literal.args[0] if literal.op == '~' else Expr('~', literal)

def _clause_from_literals(literals):
    """Rebuild a clause Expr from a list of literals, in the same canonical
    single-literal / sorted-disjunction form used elsewhere in this module."""
    literals = list(dict.fromkeys(literals))  # dedupe, preserve order
    if not literals:
        return Expr('F')
    if len(literals) == 1:
        return literals[0]
    literals.sort()
    return Expr('|', *literals)

def unit_propagate(clauses):
    """Simplify a CNF clause set via unit propagation (the same simplification
    DPLL uses internally): a unit clause satisfies every clause it appears in,
    and eliminates its complement from every clause it appears negated in.
    This is a sound, satisfiability-preserving rewrite — used here to shrink
    the clause set *before* general resolution, since raw pairwise resolution
    over a large, mostly-Horn knowledge base (like this rover's) is otherwise
    dominated by trivial unit resolutions.

    Returns (simplified_clauses: set, contradiction_found: bool).
    """
    clauses = set(clauses)
    changed = True
    while changed:
        changed = False
        unit = next((c for c in clauses if c.op not in ('|', 'F', 'T')), None)
        if unit is None:
            break
        comp = _complement(unit)
        next_clauses = {unit}
        for c in clauses:
            if c == unit:
                continue
            lits = disjuncts(c)
            if unit in lits:
                changed = True  # clause satisfied by the unit, drop it
                continue
            if comp in lits:
                remaining = [l for l in lits if l != comp]
                if not remaining:
                    return set(), True  # empty clause derived: contradiction
                next_clauses.add(_clause_from_literals(remaining))
                changed = True
            else:
                next_clauses.add(c)
        clauses = next_clauses
    return clauses, False

def pl_resolution(kb, alpha, background=None, step_budget=DEFAULT_RESOLUTION_STEP_BUDGET):
    """
    Propositional-logic resolution: say if kb entails alpha.
    kb and alpha are logic expressions.
    Returns True if KB |= alpha, False otherwise.

    `step_budget` caps the number of pairwise resolution attempts; if it's
    exhausted before either a contradiction or a fixpoint is reached, this
    reports "not entailed" (the same cautious default as DPLL's budget —
    see the module docstring).

    Implementation notes: this runs a unit-propagation pass first (sound
    simplification, see `unit_propagate`), then a "given clause" saturation
    loop — each clause is resolved against every clause that existed *before*
    it, exactly once, so work is never repeated across outer iterations the
    way a naive "resolve all pairs, repeat until fixpoint" loop would.
    Forward subsumption (dropping any new clause that is a superset of an
    already-known clause, and therefore logically redundant) keeps the
    clause set from exploding on larger knowledge bases.

    `background`, if given, is a set of clauses to treat as pure axioms for a
    Set-of-Support (SOS) restriction: two background clauses are never
    resolved together, only ever a background clause against a "support"
    clause (anything derived from the percepts/query, or from a prior
    resolution step — every resolvent joins the support set). This is sound
    unconditionally, and complete whenever the background clauses are
    satisfiable on their own — true here, since the rover's background
    axioms are just bi-conditional cell definitions with no percept
    information in them, so they never conflict with each other in
    isolation. Without this, resolving large background "signal <=> OR(
    neighbors)" clauses against each other in every direction is what makes
    naive resolution blow up on a fully-explored grid; SOS keeps the search
    focused on clauses actually relevant to the query being asked.
    """
    kb_and_not_alpha = Expr('&', kb, ~alpha)
    cnf = to_cnf(kb_and_not_alpha)
    background = background or set()

    clauses, contradiction = unit_propagate(conjuncts(cnf))
    if contradiction:
        return True
    if Expr('F') in clauses:
        return True

    clause_list = list(clauses)
    clause_set = set(clause_list)
    literal_sets = [frozenset(disjuncts(c)) for c in clause_list]
    is_background = [c in background for c in clause_list]

    def is_subsumed(new_lits):
        return any(existing <= new_lits for existing in literal_sets)

    idx = 0
    steps = 0
    while idx < len(clause_list):
        ci = clause_list[idx]
        ci_bg = is_background[idx]
        for j in range(idx):
            if ci_bg and is_background[j]:
                continue  # SOS: never combine two pure background axioms
            cj = clause_list[j]
            steps += 1
            if step_budget and steps > step_budget:
                return False  # budget exhausted: report "not proven"
            for r in pl_resolve(ci, cj):
                if r == Expr('F'):
                    return True
                if r in clause_set:
                    continue
                r_lits = frozenset(disjuncts(r))
                if is_subsumed(r_lits):
                    continue
                clause_set.add(r)
                clause_list.append(r)
                literal_sets.append(r_lits)
                is_background.append(False)  # resolvents always join support
        idx += 1

    return False

def extend(s, var, val):
    """Copy dict s and extend it by setting var to val; return copy."""
    s2 = s.copy()
    s2[var] = val
    return s2

def evaluate_clause(clause, model):
    """Evaluate a clause (disjunction of literals) under a model.
    Returns True if true, False if false, None if unknown."""
    has_unknown = False
    for literal in disjuncts(clause):
        sym, pos = (literal.args[0], False) if literal.op == '~' else (literal, True)
        if sym in model:
            if model[sym] == pos:
                return True # One true literal makes the clause true
        else:
            has_unknown = True
    if has_unknown:
        return None
    return False

def find_pure_symbol(symbols, clauses):
    """Find a symbol and its value if it appears with only one sign in clauses.

    Single pass over (clauses x their literals), tallying each symbol's
    observed polarities in a dict, rather than the naive O(|symbols| x
    |clauses| x |literals|) scan (which also allocated a fresh ~s Expr for
    every single comparison) — that naive version is what made pure-symbol
    elimination itself the dominant cost on a few-hundred-variable KB.
    """
    seen_pos, seen_neg = set(), set()
    for c in clauses:
        for literal in disjuncts(c):
            if literal.op == '~':
                sym = literal.args[0]
                if sym in symbols:
                    seen_neg.add(sym)
            else:
                if literal in symbols:
                    seen_pos.add(literal)

    for s in symbols:
        pos, neg = s in seen_pos, s in seen_neg
        if pos != neg:
            return s, pos
    return None, None

def find_unit_clause(clauses, model):
    """Find a unit clause (a clause with only one unassigned literal)."""
    for clause in clauses:
        P, value = None, None
        num_not_true = 0
        unassigned_lit = None
        
        for literal in disjuncts(clause):
            sym, pos = (literal.args[0], False) if literal.op == '~' else (literal, True)
            if sym in model:
                if model[sym] == pos:
                    # Clause is already true, this is not a unit clause for falsification
                    num_not_true = -1 
                    break
            else:
                num_not_true += 1
                unassigned_lit = literal
                
        if num_not_true == 1:
            sym, pos = (unassigned_lit.args[0], False) if unassigned_lit.op == '~' else (unassigned_lit, True)
            return sym, pos
            
    return None, None

def dpll(clauses, symbols, model, _budget=None):
    """See if the clauses are satisfiable, extending the partial model.

    Three things keep this practical on a large, mostly-Horn knowledge base
    like the rover's (dozens to hundreds of variables once the grid is
    substantially explored):

    1. Clauses already made True by `model` are dropped from `unknown_clauses`
       and every recursive call below is passed that *shrunk* list instead of
       the original `clauses` — a satisfied clause stays satisfied under any
       further (monotonic) extension of the model, so re-scanning it at every
       deeper node is pure waste.
    2. Pure-symbol elimination runs before guessing: a symbol that only ever
       appears with one polarity in the remaining clauses can be assigned
       that polarity for free, with no branching, no matter how many clauses
       it appears in.
    3. When a guess is unavoidable, the branching variable is chosen by
       simple degree (the symbol appearing in the most remaining unknown
       clauses, restricted to symbols that still actually occur in them) —
       this drives further unit propagation immediately instead of wasting a
       branch on some symbol the remaining clauses don't even mention yet.

    `_budget`, if given, is a one-element list used as a mutable node-expansion
    counter; when it hits zero this raises InferenceBudgetExceeded rather
    than continuing an exponential search (see the module docstring above).
    """
    if _budget is not None:
        if _budget[0] <= 0:
            raise InferenceBudgetExceeded()
        _budget[0] -= 1

    unknown_clauses = []
    for c in clauses:
        val = evaluate_clause(c, model)
        if val is False:
            return False
        if val is None:
            unknown_clauses.append(c)

    if not unknown_clauses:
        return True

    # Unit propagation
    P, value = find_unit_clause(unknown_clauses, model)
    if P is not None:
        return dpll(unknown_clauses, symbols, extend(model, P, value), _budget)

    # Only symbols that still occur (unassigned) in the remaining clauses can
    # possibly matter from here on — everything else is already decided or
    # irrelevant to satisfiability.
    local_symbols = set()
    for c in unknown_clauses:
        for literal in disjuncts(c):
            sym = literal.args[0] if literal.op == '~' else literal
            if sym not in model:
                local_symbols.add(sym)

    if not local_symbols:
        return False

    # Pure-symbol elimination
    P, value = find_pure_symbol(local_symbols, unknown_clauses)
    if P is not None:
        return dpll(unknown_clauses, symbols, extend(model, P, value), _budget)

    # Degree heuristic: branch on whichever unassigned symbol appears in the
    # most remaining unknown clauses.
    degree = {}
    for c in unknown_clauses:
        for literal in disjuncts(c):
            sym = literal.args[0] if literal.op == '~' else literal
            if sym in local_symbols:
                degree[sym] = degree.get(sym, 0) + 1
    P = max(degree, key=degree.get)

    if dpll(unknown_clauses, symbols, extend(model, P, True), _budget):
        return True
    if dpll(unknown_clauses, symbols, extend(model, P, False), _budget):
        return True
    return False

def dpll_satisfiable(s, node_budget=DEFAULT_DPLL_NODE_BUDGET):
    """Check satisfiability of a propositional sentence.

    Returns True/False normally, or None if the search exceeded its node
    budget without settling the question either way (see module docstring).
    """
    clauses = conjuncts(to_cnf(s))
    symbols = prop_symbols(s)
    budget = [node_budget] if node_budget else None
    try:
        return dpll(clauses, symbols, {}, budget)
    except InferenceBudgetExceeded:
        return None

def tt_entails(kb, alpha, node_budget=DEFAULT_DPLL_NODE_BUDGET):
    """Using DPLL for entailment. KB |= alpha iff (KB & ~alpha) is unsatisfiable.

    If the underlying search can't settle satisfiability within its budget,
    this reports "not entailed" — the safe, cautious direction (it never
    fabricates a "yes"), matching how the agent already treats any query it
    cannot prove.
    """
    kb_and_not_alpha = Expr('&', kb, ~alpha)
    sat = dpll_satisfiable(kb_and_not_alpha, node_budget=node_budget)
    if sat is None:
        return False
    return not sat

def entails(kb, query, method="dpll", background=None, budget=None):
    """Wrapper function to perform entailment checking.

    `background` is only used by the resolution method (see pl_resolution's
    Set-of-Support notes); DPLL doesn't need it since its degree/pure-symbol
    heuristics already make it fast on this KB without any such restriction.

    `budget` overrides the engine's default search-node/step budget for this
    one call — callers making a purely cosmetic query (e.g. "which exact
    neighbor is the hazard, for the log line") can pass a small budget so a
    hard, ambiguous query degrades to "couldn't determine" quickly instead of
    spending the full budget on something that isn't needed for the agent's
    actual move decision.
    """
    if method == "resolution":
        kwargs = {"step_budget": budget} if budget is not None else {}
        return pl_resolution(kb, query, background=background, **kwargs)
    elif method == "dpll":
        kwargs = {"node_budget": budget} if budget is not None else {}
        return tt_entails(kb, query, **kwargs)
    else:
        raise ValueError(f"Unknown inference method: {method}")
