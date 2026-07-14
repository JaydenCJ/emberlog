"""CLI behavior: subcommands, exit codes, and machine output.

Every test drives ``emberlog.cli.main`` in-process against real files in a
temp directory — the same code path as the installed console script.
"""

import json

import pytest

from emberlog import __version__


@pytest.fixture
def seeded(run, log_path):
    """A log with three entries of varying health, created via the CLI."""
    assert run("init", "-f", log_path)[0] == 0
    out = {}
    for title, extra in (
        ("Use SQLite for the job queue", ["--ttl", "90d", "--source", "agent:claude-code", "--confidence", "observed", "--tags", "storage,architecture"]),
        ("Deploys happen from main only", ["--ttl", "never", "--source", "human:alice", "--confidence", "verified"]),
        ("The flaky test is probably the cache", ["--ttl", "14d", "--confidence", "guess"]),
    ):
        code, stdout, _ = run("add", "-f", log_path, title, *extra)
        assert code == 0
        out[title] = stdout.split()[1]  # "added <id> ..."
    return out


def test_version_flag_and_bare_invocation(run, capsys):
    with pytest.raises(SystemExit) as excinfo:
        run("--version")
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"emberlog {__version__}"
    code, stdout, _ = run()  # no subcommand: help + exit 2
    assert code == 2
    assert "usage: emberlog" in stdout


def test_init_creates_file_once(run, log_path):
    code, stdout, _ = run("init", "-f", log_path, "--title", "Project Memory")
    assert code == 0
    assert f"initialized {log_path}" in stdout
    content = open(log_path, encoding="utf-8").read()
    assert content.startswith("# Project Memory")
    assert "<!-- emberlog v1 -->" in content
    code, _, stderr = run("init", "-f", log_path)  # second init must refuse
    assert code == 2
    assert "refusing to overwrite" in stderr


def test_add_reports_id_and_expiry(run, log_path):
    run("init", "-f", log_path)
    code, stdout, _ = run(
        "add", "-f", log_path, "Pin the runner image to 24.04", "--ttl", "30d"
    )
    assert code == 0
    assert '"Pin the runner image to 24.04"' in stdout
    assert "expires 2026-08-12, in 30d" in stdout  # clock pinned to 2026-07-13
    code, _, stderr = run("add", "-f", log_path, "Oops", "--ttl", "fortnight")
    assert code == 2
    assert "invalid ttl" in stderr


def test_add_body_from_stdin(run, log_path, monkeypatch):
    import io

    run("init", "-f", log_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("Longer rationale here.\n"))
    code, stdout, _ = run("add", "-f", log_path, "Piped", "--body", "-")
    assert code == 0
    assert "Longer rationale here." in open(log_path, encoding="utf-8").read()


def test_list_renders_table_and_filters(run, log_path, seeded):
    code, stdout, _ = run("list", "-f", log_path)
    assert code == 0
    header, *rows = stdout.splitlines()
    assert header.split() == ["ID", "AGE", "EXPIRES", "CONF", "SOURCE", "TITLE"]
    assert len(rows) == 3
    assert "agent:claude-code" in rows[0]
    assert "never" in rows[1]
    code, stdout, _ = run("list", "-f", log_path, "--tag", "storage")
    assert code == 0
    assert "Use SQLite" in stdout
    assert "Deploys happen" not in stdout


def test_list_json_is_parseable_and_complete(run, log_path, seeded):
    code, stdout, _ = run("list", "-f", log_path, "--json")
    assert code == 0
    payload = json.loads(stdout)
    assert [e["title"] for e in payload][0] == "Use SQLite for the job queue"
    assert payload[0]["expires"] == "2026-10-11"
    assert payload[0]["tags"] == ["storage", "architecture"]
    assert payload[1]["ttl"] == "never"
    assert payload[1]["expires"] is None


def test_show_by_prefix_and_unknown_id(run, log_path, seeded):
    full_id = seeded["Use SQLite for the job queue"]
    code, stdout, _ = run("show", "-f", log_path, full_id[:3])
    assert code == 0
    assert f"id:          {full_id}" in stdout
    assert "source:      agent:claude-code" in stdout
    code, _, stderr = run("show", "-f", log_path, "ffffff")
    assert code == 2
    assert "no entry with id" in stderr


def test_lint_clean_exit_zero(run, log_path):
    run("init", "-f", log_path)
    run("add", "-f", log_path, "Healthy", "--ttl", "90d", "--source", "human:alice")
    code, stdout, _ = run("lint", "-f", log_path)
    assert code == 0
    assert "clean — 1 active entry" in stdout


def test_lint_expired_exit_one(run, log_path, seeded, set_today):
    set_today("2026-09-01")
    code, stdout, _ = run("lint", "-f", log_path)
    assert code == 1
    assert "E101 expired" in stdout
    assert '"The flaky test is probably the cache"' in stdout


def test_lint_warnings_pass_unless_strict(run, log_path, seeded):
    # The guess entry lacks provenance and expires within 14d: warnings only.
    code, stdout, _ = run("lint", "-f", log_path)
    assert code == 0
    assert "W203 no-provenance" in stdout
    strict_code, _, _ = run("lint", "-f", log_path, "--strict")
    assert strict_code == 1


def test_lint_json_shape(run, log_path, seeded, set_today):
    set_today("2026-09-01")
    code, stdout, _ = run("lint", "-f", log_path, "--json")
    assert code == 1
    payload = json.loads(stdout)
    assert payload["ok"] is False
    assert payload["errors"] >= 1
    codes = {finding["code"] for finding in payload["findings"]}
    assert "E101" in codes
    assert all(finding["severity"] in ("error", "warning") for finding in payload["findings"])


def test_renew_updates_file(run, log_path, seeded, set_today):
    flaky_id = seeded["The flaky test is probably the cache"]
    set_today("2026-07-20")
    code, stdout, _ = run("renew", "-f", log_path, flaky_id, "--ttl", "30d")
    assert code == 0
    assert "now expires 2026-08-19" in stdout
    content = open(log_path, encoding="utf-8").read()
    assert "renewed=2026-07-20" in content


def test_verify_updates_confidence(run, log_path, seeded):
    flaky_id = seeded["The flaky test is probably the cache"]
    code, stdout, _ = run("verify", "-f", log_path, flaky_id)
    assert code == 0
    assert "confidence=verified" in stdout
    assert "checked=2026-07-13" in open(log_path, encoding="utf-8").read()


def test_retire_moves_to_archive(run, log_path, seeded, tmp_path):
    sqlite_id = seeded["Use SQLite for the job queue"]
    code, stdout, _ = run(
        "retire", "-f", log_path, sqlite_id, "--reason", "moved to Postgres after all"
    )
    assert code == 0
    assert "retired" in stdout
    archive = open(str(tmp_path / "DECISIONS.archive.md"), encoding="utf-8").read()
    assert "status=retired" in archive
    assert 'reason="moved to Postgres after all"' in archive
    assert sqlite_id not in open(log_path, encoding="utf-8").read()


def test_sweep_dry_run_then_real(run, log_path, seeded, set_today, tmp_path):
    set_today("2026-09-01")
    code, stdout, _ = run("list", "-f", log_path, "--expired")
    assert "The flaky test is probably the cache" in stdout
    assert "Use SQLite" not in stdout  # 90d ttl, still live on Sep 1
    before = open(log_path, encoding="utf-8").read()
    code, stdout, _ = run("sweep", "-f", log_path, "--dry-run")
    assert code == 0
    assert "would sweep 1 expired entry" in stdout
    assert open(log_path, encoding="utf-8").read() == before

    code, stdout, _ = run("sweep", "-f", log_path)
    assert "swept 1 expired entry" in stdout
    assert (tmp_path / "DECISIONS.archive.md").exists()
    after = open(log_path, encoding="utf-8").read()
    code, stdout, _ = run("sweep", "-f", log_path)
    assert "nothing to sweep" in stdout
    # A sweep with nothing to do must not rewrite the file.
    assert open(log_path, encoding="utf-8").read() == after


def test_stats_text_and_json(run, log_path, seeded):
    code, stdout, _ = run("stats", "-f", log_path)
    assert code == 0
    assert "active:        3" in stdout
    code, stdout, _ = run("stats", "-f", log_path, "--json")
    payload = json.loads(stdout)
    assert payload["total"] == 3
    assert payload["never"] == 1
    assert payload["by_confidence"] == {"observed": 1, "verified": 1, "guess": 1}


def test_bad_target_files_exit_2_with_hints(run, tmp_path):
    code, _, stderr = run("list", "-f", str(tmp_path / "absent.md"))
    assert code == 2
    assert "emberlog init" in stderr
    plain = tmp_path / "NOTES.md"
    plain.write_text("# Notes\n\njust prose\n", encoding="utf-8")
    code, _, stderr = run("list", "-f", str(plain))
    assert code == 2
    assert "not an emberlog file" in stderr


def test_broken_pipe_exits_quietly_like_a_unix_tool(run, log_path, seeded, monkeypatch, capsys):
    """`emberlog list | head` must not die with '[Errno 32] Broken pipe'.

    grep -q / head close the read end early; the CLI must swallow the
    resulting BrokenPipeError and exit 0, like cat/ls/grep do.
    """
    import sys as _sys

    from emberlog.cli import main as _main

    real_write = _sys.stdout.write

    def _explode(text):
        real_write(text)  # keep capsys happy for the fixture teardown
        raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setattr(_sys.stdout, "write", _explode)
    code = _main(["list", "-f", log_path])
    monkeypatch.undo()
    assert code == 0
    assert "Broken pipe" not in capsys.readouterr().err


def test_lint_summary_uses_singular_nouns(run, log_path):
    """'1 warnings' is not English — counts of one must read 'error'/'warning'."""
    run("init", "-f", log_path)
    run("add", "-f", log_path, "Only claim", "--ttl", "90d", "--confidence", "observed")
    code, stdout, _ = run("lint", "-f", log_path)  # exactly one W203 warning
    assert code == 0
    assert "1 finding (0 errors, 1 warning)" in stdout
