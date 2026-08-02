import re

def _find_matching_close(text, open_pos):
    """Given the position of an opening '(', return the position of its
    matching ')'. Correctly handles nested parens and quoted strings."""
    depth = 0
    in_string = False
    i = open_pos
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != '\\'):
            in_string = not in_string
        elif not in_string:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return len(text) - 1  # fallback

def _extract_blocks(content, keyword):
    """Find every S-expression block that starts with ``(keyword ...)``.
    Returns a list of the full text of each block (including outer parens).
    Uses bracket-counting so nested structures are handled correctly."""
    blocks = []
    pattern = re.compile(r'\(' + re.escape(keyword) + r'[\s"]')
    for m in pattern.finditer(content):
        start = m.start()
        end = _find_matching_close(content, start)
        blocks.append(content[start:end + 1])
    return blocks
