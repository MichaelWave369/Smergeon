"""Bounded log signatures. Never expose arbitrary log text in diagnostic packets."""

import re

# Only allowlisted, fixed labels and line numbers appear in Smergeon output.
# Patterns are classifications, NOT instructions extracted from log content.
SIGNATURES = (
    ("permissions", "permission denied", r"\bpermission denied\b|resource not accessible by integration|http 403\b"),
    ("dependencies", "missing Python module", r"\bModuleNotFoundError\b|\bImportError\b"),
    ("dependencies", "missing JavaScript module", r"\bcannot find module\b|ERR_MODULE_NOT_FOUND"),
    ("dependencies", "package install error", r"\bnpm ERR!\b|\bE: Unable to locate package\b"),
    ("tests", "assertion failure", r"\bAssertionError\b|\bAssertionFailedError\b"),
    ("tests", "test suite failure", r"\bFAILED \(failures=\d+\)|\bfailed [1-9][0-9]* tests?\b"),
    ("lint", "lint rule violation", r"\bruff check\b|\bESLint\b.*\berror\b|\bflake8\b.*\berror\b"),
    ("build", "TypeScript compiler error", r"\berror TS\d{4}\b"),
    ("build", "compiler error", r"\bfatal error:\b|\bSyntaxError:\b"),
    ("timeout", "timeout detected", r"\btimed out\b|\btime limit exceeded\b"),
    ("unknown", "Python traceback", r"^Traceback \(most recent call last\):"),
)

COMPILED = tuple((category, label, re.compile(pattern, re.IGNORECASE))
                 for category, label, pattern in SIGNATURES)


def scan_log(body, maximum_signals=8):
    """Return deterministic signature labels and 1-based lines, never raw log lines.

    Multiple occurrences of the same signature yield one result at the first
    matching line. Incoming logs are untrusted. This function does not retain them.
    """
    results = []
    seen = set()
    for number, line in enumerate(body.splitlines(), 1):
        # One very long line must not induce pathological regex work.
        sample = line[:2048]
        for category, label, expression in COMPILED:
            if label in seen:
                continue
            if expression.search(sample):
                seen.add(label)
                results.append({"category": category, "signature": label, "line": number})
                if len(results) >= maximum_signals:
                    return results
    return results
