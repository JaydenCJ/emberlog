"""The README Quickstart is executed verbatim — docs and code cannot drift."""

import json
import pathlib

from emberlog import __version__

README = pathlib.Path(__file__).resolve().parent.parent / "README.md"


def test_quickstart_transcript_is_reproducible(run, tmp_path, monkeypatch, set_today):
    monkeypatch.chdir(tmp_path)  # quickstart uses the default DECISIONS.md
    readme = README.read_text(encoding="utf-8")
    assert f"version-{__version__}-blue" in readme  # badge tracks the package

    run("init")
    run(
        "add", "Use SQLite for the job queue", "--ttl", "90d",
        "--source", "agent:claude-code", "--confidence", "observed",
        "--tags", "storage",
    )
    run(
        "add", "Staging resets its database every Monday", "--ttl", "45d",
        "--source", "doc:docs/runbook.md", "--confidence", "observed",
    )
    run("add", "The flaky test is probably the cache", "--ttl", "14d", "--confidence", "guess")

    _, table, _ = run("list")
    for line in (
        "6e28c8  0d   in 90d   observed  agent:claude-code    Use SQLite for the job queue",
        "be5c60  0d   in 45d   observed  doc:docs/runbook.md  Staging resets its database every Monday",
        "650dba  0d   in 14d   guess     -                    The flaky test is probably the cache",
    ):
        assert line in table  # the exact rows shown in the README
        assert line in readme

    set_today("2026-09-01")  # "seven weeks later"
    code, lint_out, _ = run("lint")
    assert code == 1
    for line in lint_out.strip().splitlines():
        assert line in readme  # every printed finding appears verbatim in the docs
    assert "4 findings (2 errors, 2 warnings)" in lint_out

    code, _, _ = run("sweep")
    assert code == 0
    code, clean_out, _ = run("lint")
    assert code == 0
    assert "clean — 1 active entry, nothing stale" in clean_out

    _, payload, _ = run("list", "--json")
    (survivor,) = json.loads(payload)
    assert survivor["title"] == "Use SQLite for the job queue"
