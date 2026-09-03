"""
kaibridge/sexpr.py -- KiCad S-expression reader and writer.

Neither parse() nor dumps() nor walk() recurses: a pathological file can
never raise RecursionError, no matter how deeply nested.

SexprError subclasses ValueError on purpose -- kicad_lib_init.listed_names()
catches ValueError and must keep working unchanged.
"""
from __future__ import annotations

__all__ = ["Quoted", "SexprError", "quote", "dumps", "parse", "parse_all",
           "head", "find", "first", "value", "walk"]

class Quoted(str):
    """A string atom that was quoted in the source and must stay quoted."""
    __slots__ = ()

class SexprError(ValueError):
    """Malformed s-expression. Always carries a line and column."""

_NEEDS_QUOTE = set(' \t\r\n()"')
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}

def quote(value):
    """Render one atom, quoting it if KiCad would."""
    text = str(value)
    if isinstance(value, Quoted) or text == "" or any(c in _NEEDS_QUOTE for c in text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text

def _tokens(text):
    """Yield (token, line, column). token is '(', ')', a bare str, or a Quoted."""
    i, n = 0, len(text)
    line, bol = 1, 0
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
            bol = i
            continue
        if c.isspace():
            i += 1
            continue
        col = i - bol + 1
        if c in "()":
            yield c, line, col
            i += 1
            continue
        if c == '"':
            i += 1
            buf = []
            while i < n and text[i] != '"':
                ch = text[i]
                if ch == "\\" and i + 1 < n:
                    buf.append(_ESCAPES.get(text[i + 1], text[i + 1]))
                    i += 2
                    continue
                if ch == "\n":
                    line += 1
                    bol = i + 1
                buf.append(ch)
                i += 1
            if i >= n:
                raise SexprError(f"unterminated string at line {line}, column {col}")
            i += 1
            yield Quoted("".join(buf)), line, col
            continue
        j = i
        while j < n and not text[j].isspace() and text[j] not in '()"':
            j += 1
        yield text[i:j], line, col
        i = j

def parse_all(text, limit=0):
    """Every top-level list in the text. limit>0 stops early."""
    trees, stack = [], []
    for token, line, col in _tokens(text):
        if token == "(":
            stack.append([])
        elif token == ")":
            if not stack:
                raise SexprError(f"unexpected ')' at line {line}, column {col}")
            done = stack.pop()
            if stack:
                stack[-1].append(done)
            else:
                trees.append(done)
                if limit and len(trees) >= limit:
                    return trees
        else:
            if not stack:
                raise SexprError(
                    f"atom '{token}' outside any list at line {line}, column {col}")
            stack[-1].append(token)
    if stack:
        raise SexprError(
            f"unbalanced parentheses: {len(stack)} list(s) still open at end of input")
    return trees

def parse(text):
    """First top-level list. Signature-compatible with the old kicad_pins.parse."""
    trees = parse_all(text, limit=1)
    if not trees:
        raise SexprError("no s-expression found")
    return trees[0]

def dumps(node, indent=-1, level=0):
    """Serialize a tree. indent < 0 -> one line (the old behaviour).
    indent >= 0 -> that many spaces per level, newline before each list child.
    """
    if not isinstance(node, list):
        return quote(node)
    pad = " " * max(indent, 0)
    out = []
    stack = [("node", node, level)]
    while stack:
        kind, item, depth = stack.pop()
        if kind == "text":
            out.append(item)
            continue
        if not isinstance(item, list):
            out.append(quote(item))
            continue
        pretty = indent >= 0 and any(isinstance(c, list) for c in item)
        out.append("(")
        stack.append(("text", ")", depth))
        if pretty:
            stack.append(("text", "\n" + pad * depth, depth))
        for index in range(len(item) - 1, -1, -1):
            child = item[index]
            stack.append(("node", child, depth + 1))
            if index:
                nl = pretty and isinstance(child, list)
                stack.append(("text", "\n" + pad * (depth + 1) if nl else " ", depth))
    return "".join(out)

def head(node, tag):
    return isinstance(node, list) and bool(node) and node[0] == tag

def find(node, tag):
    """Direct children tagged `tag`."""
    return [child for child in node if head(child, tag)]

def first(node, tag):
    for child in node:
        if head(child, tag):
            return child
    return None

def value(node, tag, default=None):
    """The single argument of the first (tag X) child."""
    child = first(node, tag)
    if child is not None and len(child) > 1:
        return child[1]
    return default

def walk(node, tag=None):
    """Depth-first over every list in the tree, without recursion."""
    stack = [node]
    while stack:
        item = stack.pop()
        if not isinstance(item, list):
            continue
        if tag is None or head(item, tag):
            yield item
        for child in reversed(item):
            if isinstance(child, list):
                stack.append(child)
