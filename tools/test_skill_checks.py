#!/usr/bin/env python3
"""Behavioral test for the skill-library checks.

Verifies three behaviors introduced for mixed bundled/user skill libraries:

1. Hidden/archive directories (``.archive``, ``.curator_backups``, ``.hub``)
   are skipped by ``_iter_skills``, so archived/backup skill copies never
   produce false positives.
2. ``check_skills`` labels Hermes-bundled skills (tracked in
   ``.bundled_manifest``) with ``[bundled]``, separating user-fixable issues
   from Hermes-managed ones — matched by the skill's declared ``name`` (not
   the directory basename), so a nested user skill that merely shares a
   basename with a bundled skill is not mislabeled.
3. ``check_commands`` includes each skill's ``version`` in slug-collision
   messages, so a stale unversioned copy is distinguishable from a newer
   versioned one at a glance.

Uses a synthetic ``$HERMES_HOME`` (monkeypatched) so it does not touch the
real install and does not require the ``hermes`` CLI.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _build_home(root: Path) -> None:
    _write(root / "skills/.bundled_manifest", "dogfood:abc123\nbundled-broken:def456\n")
    _write(root / "skills/dogfood/SKILL.md", "---\nname: dogfood\ndescription: bundled skill\n---\nbody\n")
    _write(root / "skills/bundled-broken/SKILL.md", "just text no frontmatter")
    _write(root / "skills/user-broken/SKILL.md", "also no frontmatter")
    # nested user skill whose basename collides with a bundled name but whose
    # frontmatter has no `name` — the fix must NOT label this [bundled]
    _write(root / "skills/user-collection/dogfood/SKILL.md", "---\ndescription: user skill, no name\n---\nbody\n")
    _write(root / "skills/foo/SKILL.md", "---\nname: foo\ndescription: old\n---\nold\n")
    _write(root / "skills/category/foo/SKILL.md", "---\nname: foo\ndescription: new\nversion: 1.2.0\n---\nnew\n")
    _write(root / "skills/.archive/foo-old/SKILL.md", "---\nname: foo\ndescription: archived\nversion: 0.1.0\n---\narchived\n")
    _write(root / "skills/plain/SKILL.md", "---\nname: plain\ndescription: p\nversion: 2.0.0\n---\nbody\n")


def main(argv: list[str]) -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td) / "hermes_guide"
        pkg.mkdir()
        for name in ("__init__.py", "checks.py", "constants.py"):
            shutil.copy(REPO / name, pkg / name)
        sys.path.insert(0, td)

        import hermes_guide.checks as checks  # noqa: E402

        home = Path(td) / "home"
        _build_home(home)

        checks._cache.clear()
        checks._hermes_home = lambda: str(home)

        # (1) hidden/archive dirs are skipped
        walked = list(checks._iter_skills())
        if len(walked) != 7:
            failures.append(f"expected 7 skills (hidden .archive skipped), got {len(walked)}")
        if any(".archive" in d for d, _ in walked):
            failures.append("hidden .archive dir was not skipped")

        # (2) bundled skills are labelled by declared name, not basename
        sr = checks.check_skills()
        sdetail = sr.get("detail") or []
        if sr["status"] != "broken" or sr["reason"] != "3 skill issue(s)":
            failures.append(f"check_skills unexpected: {sr['status']} - {sr['reason']}")
        if not any("bundled-broken" in d and "[bundled]" in d for d in sdetail):
            failures.append("bundled skill not labelled [bundled]")
        if any("user-broken" in d and "[bundled]" in d for d in sdetail):
            failures.append("user skill wrongly labelled [bundled]")
        # the nested user skill shares basename `dogfood` with a bundled skill
        # but has no declared `name`; it must NOT be labelled [bundled]
        nested = [d for d in sdetail if "user-collection/dogfood" in d]
        if not nested:
            failures.append("nested user skill with no name not flagged")
        elif "[bundled]" in nested[0]:
            failures.append(f"nested user skill mislabelled [bundled]: {nested[0]}")

        # (3) collision messages carry versions and skip archived copies
        cr = checks.check_commands()
        cdetail = cr.get("detail") or []
        coll = [d for d in cdetail if "normalize to" in d]
        if len(coll) != 1:
            failures.append(f"expected exactly 1 collision, got {len(coll)}")
        elif "v1.2.0" not in coll[0] or "unversioned" not in coll[0]:
            failures.append(f"version info missing from collision: {coll[0]}")
        elif "foo-old" in coll[0]:
            failures.append("archived skill leaked into collision")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1
    print("OK: skill-library checks behave as expected (bundled label, hidden-dir skip, versioned collisions)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
