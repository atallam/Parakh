"""Metric exit conditions: a tiny, safe expression language (plan 05 §2.4, D13).

    revenue_growth_yoy_pct < -10
    pledge_pct > 0.25 and roce_5y_avg < 0.12
    (pe_ttm > 60 or value_score < 40) and momentum_score < 45

Comparisons of a named variable with a number, joined by `and` / `or` (and parentheses). Nothing
is evaluated with `eval`. A variable with no value makes its comparison UNKNOWN, never false:
`True or UNKNOWN` is True, `False and UNKNOWN` is False, anything else involving UNKNOWN is
UNKNOWN, and an UNKNOWN breaker is shown as ❔, never as clean (UX-05).
"""

from __future__ import annotations

import operator
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

TOKEN = re.compile(
    r"\s*(?:(?P<num>-?\d+(?:\.\d+)?)|(?P<id>[A-Za-z_][A-Za-z0-9_]*)|(?P<op><=|>=|==|!=|<|>)|(?P<par>[()]))"
)
OPS: dict[str, Callable[[float, float], bool]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}


class RuleError(ValueError):
    pass


@dataclass
class Result:
    value: bool | None  # None = unknown
    used: dict[str, float] = field(default_factory=dict)  # variable → value
    missing: list[str] = field(default_factory=list)


def _tokens(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    pos = 0
    text = text.strip()
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise RuleError(f"cannot read the rule at: {text[pos : pos + 12]!r}")
        pos = m.end()
        if m.group("num"):
            out.append(("num", m.group("num")))
        elif m.group("id"):
            word = m.group("id")
            out.append(("kw" if word in ("and", "or") else "id", word))
        elif m.group("op"):
            out.append(("op", m.group("op")))
        else:
            out.append(("par", m.group("par")))
    if not out:
        raise RuleError("the rule is empty")
    return out


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.t, self.i = tokens, 0

    def peek(self) -> tuple[str, str] | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self) -> tuple[str, str]:
        tok = self.peek()
        if tok is None:
            raise RuleError("the rule ends too soon")
        self.i += 1
        return tok

    def parse(self) -> tuple:
        node = self.or_()
        if self.peek() is not None:
            raise RuleError(f"unexpected {self.peek()[1]!r} after the condition")  # type: ignore[index]
        return node

    def or_(self) -> tuple:
        node = self.and_()
        while self.peek() == ("kw", "or"):
            self.take()
            node = ("or", node, self.and_())
        return node

    def and_(self) -> tuple:
        node = self.atom()
        while self.peek() == ("kw", "and"):
            self.take()
            node = ("and", node, self.atom())
        return node

    def atom(self) -> tuple:
        kind, val = self.take()
        if (kind, val) == ("par", "("):
            node = self.or_()
            if self.take() != ("par", ")"):
                raise RuleError("missing )")
            return node
        if kind != "id":
            raise RuleError(f"expected a variable name, found {val!r}")
        k2, op = self.take()
        if k2 != "op":
            raise RuleError(f"expected a comparison after {val!r}")
        k3, num = self.take()
        if k3 != "num":
            raise RuleError(f"expected a number after {op!r}")
        return ("cmp", val, op, float(num))


def parse(text: str) -> tuple:
    return _Parser(_tokens(text)).parse()


def variables_in(text: str) -> set[str]:
    out: set[str] = set()

    def walk(n: tuple) -> None:
        if n[0] == "cmp":
            out.add(n[1])
        else:
            walk(n[1])
            walk(n[2])

    walk(parse(text))
    return out


def evaluate(text: str, lookup: Callable[[str], float | None]) -> Result:
    tree = parse(text)
    res = Result(None)

    def go(n: tuple) -> bool | None:
        if n[0] == "cmp":
            _, name, op, num = n
            v = lookup(name)
            if v is None:
                if name not in res.missing:
                    res.missing.append(name)
                return None
            res.used[name] = v
            return OPS[op](v, num)
        a, b = go(n[1]), go(n[2])
        if n[0] == "and":
            if a is False or b is False:
                return False
            return None if a is None or b is None else True
        if a is True or b is True:
            return True
        return None if a is None or b is None else False

    res.value = go(tree)
    return res


def check_variables(text: str, known: Iterable[str]) -> list[str]:
    """Names in the rule that no variable provides (typo guard at validation time)."""
    known_set = set(known)
    return sorted(v for v in variables_in(text) if v not in known_set)
