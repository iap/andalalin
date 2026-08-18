# Security Policy

## Supported Versions

Only the latest published version (`0.1.0`) receives security fixes.

| Version | Supported |
| --- | --- |
| 0.1.0 | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly by
opening a [private security advisory](https://github.com/iap/hermes-guide/security/advisories/new). We will respond as soon as possible and work with you to address the issue.

Please do not publicly disclose the vulnerability until it has been resolved.

## Read-only Guarantee

This plugin never writes to Hermes configuration or the filesystem — in normal
operation, or during install/uninstall. It only reads config (`hermes config
path`), parses SKILL.md / bundle files, and runs read-only `hermes ... doctor`
subcommands. The only plugin-scoped setting it declares is the opt-in
`proactive` boolean (see `plugin.yaml` `config_schema`); it does not touch any
other core Hermes config.

This contract is enforced in CI by `tools/check_no_mutation.py`, which fails the
build if any Python source introduces a write-mode `open()`, `yaml.dump()` /
`json.dump()`, `Path.write_text()`, `os.remove()`, `shutil.*`, or a mutating
subprocess (`pip`/`install`/`uninstall`).
