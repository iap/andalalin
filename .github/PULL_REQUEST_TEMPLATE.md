## What / Why

## Verification
- [ ] Local CI gates green: `py_compile`, `hermes plugins doctor . --ci`, `check_self_claim`, `check_no_mutation` (selftest + scan), `test_readonly_runtime`, `test_mcp_shape`
- [ ] Changed `SKILL.md` files have version bumps (`tools/check_skill_version_bump.py`)
- [ ] Facts verified against installed/upstream Hermes source (cite file + lines)
- [ ] `.github/upstream-drift.baseline` bumped if this absorbs upstream drift
