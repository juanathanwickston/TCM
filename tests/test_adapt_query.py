"""
Tests for adapt_query() function.

Verifies safe placeholder conversion from SQLite (?) to psycopg2 (%s).
Must NOT corrupt placeholders inside quotes or comments.

This test is self-contained - does not import db.py to avoid psycopg2 dependency.
"""


def adapt_query(sql: str) -> str:
    """
    Convert SQLite-style '?' placeholders to psycopg2 '%s' placeholders,
    but ONLY when the '?' is outside of:
      - single-quoted strings: '...'
      - double-quoted identifiers: "..."
      - line comments: -- ...
      - block comments: /* ... */
    """
    if not sql:
        return sql

    out = []
    i = 0
    n = len(sql)

    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False

    while i < n:
        ch = sql[i]

        # End line comment
        if in_line_comment:
            out.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        # End block comment
        if in_block_comment:
            out.append(ch)
            if ch == "*" and i + 1 < n and sql[i + 1] == "/":
                out.append("/")
                i += 2
                in_block_comment = False
            else:
                i += 1
            continue

        # Start comments (only if not in quotes)
        if not in_single and not in_double:
            if ch == "-" and i + 1 < n and sql[i + 1] == "-":
                out.append(ch)
                out.append("-")
                i += 2
                in_line_comment = True
                continue
            if ch == "/" and i + 1 < n and sql[i + 1] == "*":
                out.append(ch)
                out.append("*")
                i += 2
                in_block_comment = True
                continue

        # Handle quotes
        if ch == "'" and not in_double:
            out.append(ch)
            if in_single:
                if i + 1 < n and sql[i + 1] == "'":
                    out.append("'")
                    i += 2
                    continue
                in_single = False
            else:
                in_single = True
            i += 1
            continue

        if ch == '"' and not in_single:
            out.append(ch)
            if in_double:
                if i + 1 < n and sql[i + 1] == '"':
                    out.append('"')
                    i += 2
                    continue
                in_double = False
            else:
                in_double = True
            i += 1
            continue

        # Replace placeholder only when not in quotes/comments
        if ch == "?" and not in_single and not in_double:
            out.append("%s")
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def test_simple():
    """Simple query with one placeholder."""
    assert adapt_query("SELECT * WHERE id = ?") == "SELECT * WHERE id = %s"


def test_multi():
    """Multiple placeholders in sequence."""
    result = adapt_query("INSERT INTO t VALUES (?, ?, ?)")
    assert result == "INSERT INTO t VALUES (%s, %s, %s)"


def test_in_string():
    """Placeholder character inside string literal should NOT be converted."""
    result = adapt_query("SELECT * WHERE name = 'What?'")
    assert result == "SELECT * WHERE name = 'What?'"


def test_mixed():
    """Mix of literal question marks and real placeholders."""
    result = adapt_query("SELECT * WHERE name = 'What?' AND id = ?")
    assert result == "SELECT * WHERE name = 'What?' AND id = %s"


def test_line_comment():
    """Question mark in -- comment should NOT be converted."""
    result = adapt_query("SELECT * -- is this okay?\nWHERE id = ?")
    assert result == "SELECT * -- is this okay?\nWHERE id = %s"


def test_block_comment():
    """Question mark inside block comment /* ... */ should NOT be converted."""
    result = adapt_query("SELECT * /* what? */ WHERE id = ?")
    assert result == "SELECT * /* what? */ WHERE id = %s"


def test_escaped_quote():
    """Escaped single quote ('') should not break parsing."""
    result = adapt_query("SELECT * WHERE name = 'O''Brien?' AND id = ?")
    assert result == "SELECT * WHERE name = 'O''Brien?' AND id = %s"


def test_double_quoted_identifier():
    """Question mark in double-quoted identifier should NOT be converted."""
    result = adapt_query('SELECT "what?" FROM t WHERE id = ?')
    assert result == 'SELECT "what?" FROM t WHERE id = %s'


def test_empty():
    """Empty string returns empty string."""
    assert adapt_query("") == ""


def test_none():
    """None returns None."""
    assert adapt_query(None) is None


if __name__ == "__main__":
    # Run all tests
    test_simple()
    print("PASS: test_simple")
    
    test_multi()
    print("PASS: test_multi")
    
    test_in_string()
    print("PASS: test_in_string")
    
    test_mixed()
    print("PASS: test_mixed")
    
    test_line_comment()
    print("PASS: test_line_comment")
    
    test_block_comment()
    print("PASS: test_block_comment")
    
    test_escaped_quote()
    print("PASS: test_escaped_quote")
    
    test_double_quoted_identifier()
    print("PASS: test_double_quoted_identifier")
    
    test_empty()
    print("PASS: test_empty")
    
    test_none()
    print("PASS: test_none")
    
    print("\n" + "="*50)
    print("ALL TESTS PASSED")
    print("="*50)
