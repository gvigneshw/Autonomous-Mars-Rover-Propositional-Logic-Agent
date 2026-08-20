class Expr:
    """A propositional logic expression."""
    def __init__(self, op, *args):
        self.op = op
        self.args = tuple(args)

    def __eq__(self, other):
        return isinstance(other, Expr) and self.op == other.op and self.args == other.args

    def __hash__(self):
        return hash((self.op, self.args))

    def __repr__(self):
        if not self.args:
            return str(self.op)
        if len(self.args) == 1:
            return f"{self.op}{self.args[0]}"
        return f"({f' {self.op} '.join(map(str, self.args))})"

    def __invert__(self):
        return Expr('~', self)

    def __and__(self, other):
        return Expr('&', self, other)

    def __or__(self, other):
        return Expr('|', self, other)

    def __rshift__(self, other):
        return Expr('>>', self, other)

    def __lshift__(self, other):
        return Expr('<<', self, other)
        
    def __lt__(self, other):
        # Allow sorting for canonical form
        return repr(self) < repr(other)

def Symbol(name):
    return Expr(name)

def equiv(a, b):
    return Expr('<=>', a, b)

def eliminate_implications(s):
    if not s.args:
        return s
    args = tuple(eliminate_implications(arg) for arg in s.args)
    if s.op == '>>':
        return Expr('|', Expr('~', args[0]), args[1])
    elif s.op == '<<':
        return Expr('|', args[0], Expr('~', args[1]))
    elif s.op == '<=>':
        return Expr('&', Expr('|', Expr('~', args[0]), args[1]), Expr('|', args[0], Expr('~', args[1])))
    else:
        return Expr(s.op, *args)

def move_not_inwards(s):
    if s.op == '~':
        not_s = s.args[0]
        if not not_s.args:
            return s
        if not_s.op == '~':
            return move_not_inwards(not_s.args[0])
        if not_s.op == '&':
            return Expr('|', *[move_not_inwards(Expr('~', arg)) for arg in not_s.args])
        if not_s.op == '|':
            return Expr('&', *[move_not_inwards(Expr('~', arg)) for arg in not_s.args])
        return Expr('~', move_not_inwards(not_s))
    elif s.args:
        return Expr(s.op, *[move_not_inwards(arg) for arg in s.args])
    return s

def distribute_and_over_or(s):
    if s.op == '|':
        s = Expr('|', *[distribute_and_over_or(arg) for arg in s.args])
        if len(s.args) == 0:
            return s
        if len(s.args) == 1:
            return s.args[0]
        
        and_arg = None
        other_args = []
        for arg in s.args:
            if arg.op == '&' and and_arg is None:
                and_arg = arg
            else:
                other_args.append(arg)
                
        if and_arg is not None:
            others_or = Expr('|', *other_args)
            return Expr('&', *[distribute_and_over_or(Expr('|', a, others_or)) for a in and_arg.args])
        else:
            return s
    elif s.op == '&':
        return Expr('&', *[distribute_and_over_or(arg) for arg in s.args])
    return s

def flatten(s):
    if not s.args:
        return s
    if s.op == '~':
        return Expr('~', flatten(s.args[0]))
    
    args = []
    for arg in s.args:
        arg = flatten(arg)
        if arg.op == s.op:
            args.extend(arg.args)
        else:
            args.append(arg)
            
    if len(args) == 1 and s.op in ('&', '|'):
        return args[0]
    return Expr(s.op, *args)

def to_cnf(s):
    """Convert a propositional logic sentence to Conjunctive Normal Form."""
    s = eliminate_implications(s)
    s = move_not_inwards(s)
    
    # We might need to distribute multiple times if there are nested structures
    # A simple way is to loop until it doesn't change
    while True:
        s = flatten(s)
        next_s = distribute_and_over_or(s)
        next_s = flatten(next_s)
        if next_s == s:
            break
        s = next_s
    
    return s

def disjuncts(s):
    """Return a list of the disjuncts in the sentence s."""
    if s.op == '|':
        return list(s.args)
    elif s.op == 'F': # False
        return []
    else:
        return [s]

def conjuncts(s):
    """Return a list of the conjuncts in the sentence s."""
    if s.op == '&':
        return list(s.args)
    elif s.op == 'T': # True
        return []
    else:
        return [s]

def is_symbol(s):
    return not s.args and isinstance(s.op, str)

def prop_symbols(s):
    """Return a set of all propositional symbols in sentence s."""
    if is_symbol(s):
        return {s}
    symbols = set()
    for arg in s.args:
        symbols.update(prop_symbols(arg))
    return symbols
