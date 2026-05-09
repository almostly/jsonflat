# jsonflat project conventions

## Comment style for section dividers

Use the 80-character dashed style — not Unicode box-drawing characters.
Note the space after `#`; this matches `ruff format`'s default and PEP 8.

```python
# -------------------------------------------------------------------------------
# Section name
# -------------------------------------------------------------------------------
```

No blank line between the closing `# ---` line and the next code block.

Do NOT use: `# ── Section ──────────────────────────────────────────────────────`

## Assignment formatting

No aligned `=` signs. One space on each side only:

```python
# correct
foo = "bar"
longer_name = "baz"

# wrong
foo         = "bar"
longer_name = "baz"
```

## F-string formatting

No extra spaces inside f-strings around interpolated values:

```python
# correct
f"value={var}"
f"{a} and {b}"

# wrong
f"value=   {var}"
f"    {var}"
f"{var} "
```

## Type checking

Never use `# type: ignore` (or any of its variants). If the type checker complains, change the design until the types are honest.

`# type: ignore` is never the answer in this codebase.
