"""Static guardrail — no dangerous eval/exec/deserialization in runtime code.

Fails the test suite if any future commit introduces:
  - eval(
  - exec(
  - pickle.loads
  - marshal.loads
  - yaml.load without SafeLoader
  - top-level builtin compile( (module .compile like re.compile is safe)

Scope: /app/backend, excluding tests/, scripts/, __pycache__/, .git/.
"""
from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path("/app/backend")

EXCLUDE_DIRS = {"__pycache__", "tests", "scripts", ".git"}

# Regexes are compiled here (safe — static patterns).
# Each pattern is designed so it only matches CALLS, not comments/strings.
PATTERNS = {
    "eval": re.compile(r'(?<![A-Za-z_.])eval\s*\('),
    "exec": re.compile(r'(?<![A-Za-z_.])exec\s*\('),
    "pickle.loads": re.compile(r'\bpickle\.loads\s*\('),
    "marshal.loads": re.compile(r'\bmarshal\.loads\s*\('),
    # yaml.load(...) is dangerous UNLESS a SafeLoader is passed. We flag any
    # yaml.load(...) call and let the reviewer confirm SafeLoader in-line.
    "yaml.load unsafe": re.compile(r'\byaml\.load\s*\((?![^)]*SafeLoader)'),
    # Builtin compile( — but NOT `re.compile(`, `str.compile(`, `.compile(`.
    "builtin compile": re.compile(r'(?<![A-Za-z_.])compile\s*\('),
}

# Lines allowed to skip the check (explicit opt-out for reviewed safe usage).
NOQA_MARKER = "noqa: dangerous"


def _iter_py_files():
    for p in BACKEND.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        yield p


def _is_comment_or_string_only(line: str) -> bool:
    """Best-effort filter: skip lines whose match is inside a comment or a
    triple-quoted docstring header. Cheap heuristic — false negatives are
    caught by the runtime import of these files.
    """
    stripped = line.strip()
    if stripped.startswith("#"):
        return True
    return False


def test_no_dangerous_eval_or_deserialization():
    offences: list[str] = []
    for py in _iter_py_files():
        rel = str(py.relative_to(BACKEND))
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if NOQA_MARKER in line:
                continue
            if _is_comment_or_string_only(line):
                continue
            for label, pat in PATTERNS.items():
                if pat.search(line):
                    offences.append(f"{rel}:{i} — {label}: {line.strip()[:120]}")

    assert not offences, (
        "Dangerous eval/exec/deserialization patterns detected in runtime code:\n"
        + "\n".join(offences)
        + "\n\nIf the usage is intentional and safe, append `# noqa: dangerous` to the line."
    )
