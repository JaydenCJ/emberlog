# Contributing to emberlog

Thanks for your interest in contributing. Issues, discussions, and pull
requests are all welcome.

## Development setup

```bash
git clone https://github.com/JaydenCJ/emberlog
cd emberlog
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the checks

```bash
pytest                 # 92 deterministic tests, all offline
bash scripts/smoke.sh  # end-to-end CLI lifecycle; must print SMOKE OK
```

Both must pass before a pull request is reviewed. The suite pins its clock
with `EMBERLOG_TODAY`, so it runs fully offline and never flakes on dates.

## Ground rules

- **No new runtime dependencies.** The package is standard-library only;
  that is a feature. Test-only dependencies belong in the `dev` extra.
- **Format changes need docs and healing.** Anything that changes the
  meaning of an ember field must update `docs/format.md`, keep old files
  parseable, and never delete what a human typed — lossless round-trip is
  a hard invariant (see the writer/parser fixed-point test).
- **The linter must stay deterministic.** New rules take their inputs from
  the parsed document and the injectable clock only — no filesystem
  mtimes, no locale, no network.
- **Every public API needs an English docstring and a test.** The README
  quickstart is executed verbatim by `tests/test_readme_example.py`; keep
  code and docs in sync.
- **Keep the three READMEs aligned.** `README.md`, `README.zh.md`, and
  `README.ja.md` are line-for-line parallel; update all three when you
  change one (English is the authoritative version).

## Reporting bugs

Please include `emberlog --version`, the log file (or a minimal entry that
reproduces the problem — the format is plain text, easy to trim), the
`EMBERLOG_TODAY` value if you pinned one, and the full lint output.

## Security

Please do not open public issues for suspected vulnerabilities; use
GitHub's private vulnerability reporting on this repository instead.
