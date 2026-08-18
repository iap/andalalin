#!/usr/bin/env python3
"""Fail if plugin Python source mutates config or the filesystem.

Hermes plugins must be read-only: observe and report, never write. This guard
parses the plugin's Python sources with ``ast`` and exits non-zero when it finds
filesystem writes, config mutation, or mutating subprocesses.

Scope note: this is a *developer-discipline lint* — it catches obvious or
accidental writes and keeps contributors honest. It is NOT a security boundary.
The hard boundary is the plugin's absence of a ``capabilities:`` block (see
``plugin.yaml``), which grants zero privileged write permissions regardless of
what the code says. A determined actor can always obfuscate a write past any
static check; the capabilities model is what actually blocks it at runtime.

AST parsing (rather than line-based regex) makes the guard multiline-aware, so a
write call split across lines can't slip through. Scanned: ``*.py`` under the
repo root, excluding ``tools/`` (CI-time utilities).

Style and CI wiring mirror tools/check_self_claim.py.

Usage:
    python tools/check_no_mutation.py            # scan plugin Python sources
    python tools/check_no_mutation.py --selftest # regression-check the detector
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# CI-time utilities excluded from the scan (not plugin runtime code).
_EXCLUDE_DIRS = {"tools"}

# A "mode" string is a write mode if it contains any of these flags.
_WRITE_FLAGS = "wax+"

# Subprocess invocations that indicate mutation. Token-based (not substring)
# so `pipeline`, `installer`, etc. don't false positive.
_MUTATING_SUBPROCESS_TOKENS = {"pip", "pip3", "install", "uninstall"}

# pathlib.Path mutating methods — flagged on any receiver.
# NOTE: `rename` and `replace` are handled separately below (arity check),
# because `str.replace()` is a read-only string method that would false
# positive. The os.* forms (os.rename/os.replace) are caught by the os
# receiver check.
_PATH_MUTATING_METHODS = {
    "write_text", "write_bytes",  # file content
    "mkdir", "touch",             # create dir/file
    "unlink", "rmdir",            # delete file/dir
    "symlink_to", "hardlink_to",  # links
    "chmod",                      # permissions
}

# os / shutil / tempfile mutation functions.
_OS_MUTATIONS = {
    "remove", "unlink", "rename", "replace", "mkdir", "makedirs",
    "chmod", "chown", "utime", "link", "symlink", "mkfifo", "truncate",
}
_SHUTIL_MUTATIONS = {
    "rmtree", "move", "copy", "copy2", "copyfile", "copytree",
    "make_archive", "unpack_archive", "chown",
}
_TEMPFILE_MUTATIONS = {
    "TemporaryFile", "NamedTemporaryFile", "SpooledTemporaryFile",
    "mkstemp", "mkdtemp", "TemporaryDirectory",
}


def _is_write_mode(node: ast.AST) -> bool:
    """True if `node` is a string literal representing a write mode."""
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and any(flag in node.value for flag in _WRITE_FLAGS)
    )


def _open_mode_is_write(call: ast.Call) -> bool:
    """True if an open()/Path.open() call opens a path for writing."""
    func = call.func

    for kw in call.keywords:
        if kw.arg == "mode" and _is_write_mode(kw.value):
            return True

    if isinstance(func, ast.Name):
        # Builtin open(file, mode, ...): mode is the 2nd positional arg.
        return len(call.args) >= 2 and _is_write_mode(call.args[1])

    if isinstance(func, ast.Attribute):
        # Path.open(mode, ...) puts mode first; io.open(file, mode) puts it
        # second. Check the first two positional args to cover both.
        return any(_is_write_mode(arg) for arg in call.args[:2])

    return False


def _iter_string_literals(node: ast.AST):
    """Yield every string literal found within an AST node."""
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            yield child.value


def _subprocess_mutates(call: ast.Call) -> bool:
    """True if a subprocess call mentions pip/install/uninstall as a token."""
    for value in _iter_string_literals(call):
        if any(tok in _MUTATING_SUBPROCESS_TOKENS for tok in value.lower().split()):
            return True
    return False


def _detect(tree: ast.AST) -> list[tuple[int, str]]:
    """Return (lineno, label) for every mutation detected in `tree`."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func

        # open() / Path.open()
        if (isinstance(func, ast.Name) and func.id == "open") or (
            isinstance(func, ast.Attribute) and func.attr == "open"
        ):
            if _open_mode_is_write(node):
                hits.append((node.lineno, "write-mode open()/Path.open()"))
                continue

        # yaml.dump / yaml.safe_dump / json.dump
        if (
            isinstance(func, ast.Attribute)
            and func.attr in ("dump", "safe_dump")
            and isinstance(func.value, ast.Name)
            and func.value.id in ("yaml", "json")
        ):
            mod = func.value.id
            # json.dump() always needs a writable fp; yaml.dump()/safe_dump()
            # only write when a stream is passed — single-arg yaml.dump returns
            # a string and must not false positive.
            if mod == "json" or len(node.args) >= 2 or any(
                kw.arg == "stream" for kw in node.keywords
            ):
                hits.append((node.lineno, f"{mod}.{func.attr}()"))
            continue

        # os / shutil / tempfile / subprocess module calls
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            mod = func.value.id
            if mod == "os" and func.attr in _OS_MUTATIONS:
                hits.append((node.lineno, f"os.{func.attr}()"))
                continue
            if mod == "shutil" and func.attr in _SHUTIL_MUTATIONS:
                hits.append((node.lineno, f"shutil.{func.attr}()"))
                continue
            if mod == "tempfile" and func.attr in _TEMPFILE_MUTATIONS:
                hits.append((node.lineno, f"tempfile.{func.attr}()"))
                continue
            if mod == "subprocess" and _subprocess_mutates(node):
                hits.append((node.lineno, "mutating subprocess (pip/install/uninstall)"))
                continue

        # pathlib mutating methods (any receiver)
        if isinstance(func, ast.Attribute) and func.attr in _PATH_MUTATING_METHODS:
            hits.append((node.lineno, f".{func.attr}()"))
            continue

        # Path.rename(target) / Path.replace(target) mutate the filesystem but
        # share their names with str.replace(old, new) (read-only). Distinguish
        # by arity: str.replace takes 2+ args (positional or old=/new=), the
        # pathlib forms take exactly one target (positional or target=).
        if (
            isinstance(func, ast.Attribute)
            and func.attr in ("rename", "replace")
            and len(node.args) + len(node.keywords) == 1
        ):
            hits.append((node.lineno, f".{func.attr}()"))
            continue

    return hits


def detect_code(source: str) -> list[str]:
    """Parse a source string and return the mutation labels it contains."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [label for _, label in _detect(tree)]


def scan(path: Path) -> list[str]:
    """Return "path:lineno: [label] line" strings for every mutation in `path`."""
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
    except Exception:
        return []
    lines = source.splitlines()
    hits: list[str] = []
    for lineno, label in _detect(tree):
        line_text = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""
        hits.append(f"{path}:{lineno}: [{label}] {line_text}")
    return hits


# Regression table: (snippet, should_be_detected). Covers open() signatures,
# keyword/positional/multiline modes, pathlib writes, module functions, and
# read-only negatives.
_SELFTEST_CASES: list[tuple[str, bool]] = [
    ('open(path, "r", encoding="utf-8")', False),
    ('open(path, "w")', True),
    ('open(path, "a", encoding="utf-8")', True),
    ('open(path, "rb")', False),
    ('open(path, "wb")', True),
    ('open(path, "r+")', True),
    ('open(path, mode="w")', True),
    ('open(path, mode="r")', False),
    ('Path("out").open("w")', True),
    ('Path("out").open("r")', False),
    ('Path("out").open("wb")', True),
    ('Path("out").open(mode="a")', True),
    ('Path("out").open(\n    "w"\n)', True),  # multiline write must be caught
    ("Path('out').mkdir()", True),
    ("Path('out').touch()", True),
    ("Path('out').unlink()", True),
    ("Path('out').rmdir()", True),
    ("os.rename('a', 'b')", True),
    ("os.replace('a', 'b')", True),
    ('s.replace(" ", "-")', False),  # str.replace is read-only — must NOT flag
    ('name.replace(" ", "-").replace("_", "-")', False),  # chained str.replace
    ("Path('a').rename('b')", True),
    ("Path('a').replace('b')", True),
    ("Path('out').symlink_to('x')", True),
    ("Path('x').write_text(s)", True),
    ("yaml.dump(data, f)", True),
    ("yaml.safe_load(text)", False),
    ("json.dump(data, f)", True),
    ("os.remove(p)", True),
    ("os.makedirs(p)", True),
    ("os.chmod(p, 0o600)", True),
    ("os.symlink(a, b)", True),
    ("shutil.rmtree(p)", True),
    ("shutil.copytree(a, b)", True),
    ("tempfile.NamedTemporaryFile()", True),
    ("tempfile.mkdtemp()", True),
    ('subprocess.run(["hermes", "config", "path"])', False),
    ('subprocess.run(["pip", "install", "x"])', True),
    ('subprocess.run(["echo", "pipeline installer"])', False),  # token, not substring
    ("yaml.dump(data)", False),  # no stream -> returns str, read-only
    ("yaml.safe_dump(data)", False),
    ("yaml.dump(data, stream=f)", True),
    ("Path('a').rename(target='b')", True),  # keyword target form
]


def selftest() -> int:
    """Verify the detector against the regression table; exit non-zero on drift."""
    failures = 0
    for snippet, expect in _SELFTEST_CASES:
        detected = bool(detect_code(snippet))
        if detected != expect:
            failures += 1
            print(
                f"SELFTEST FAIL: expected detected={expect} got={detected} for: {snippet!r}",
                file=sys.stderr,
            )
    if failures:
        print(f"{failures} selftest case(s) failed", file=sys.stderr)
        return 1
    print(f"selftest OK: {len(_SELFTEST_CASES)} cases")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()

    root = Path(argv[1]) if len(argv) > 1 else Path(".")
    targets = [
        p
        for p in sorted(root.rglob("*.py"))
        if not any(part in _EXCLUDE_DIRS for part in p.relative_to(root).parts)
    ]
    if not targets:
        print("No Python files found to scan", file=sys.stderr)
        return 1

    hits: list[str] = []
    for path in targets:
        hits.extend(scan(path))

    if hits:
        print("Mutation found in plugin Python source:", file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        print(
            f"\n{len(hits)} mutation(s). Plugins must be read-only — remove the write or document an explicit exception.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {len(targets)} Python file(s) scanned, no mutation detected")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
