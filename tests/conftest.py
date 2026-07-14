"""Shared fixtures: a pinned clock, a temp log, and a CLI runner.

Every test runs under a frozen ``EMBERLOG_TODAY`` so expiry math is
byte-stable no matter when the suite executes — determinism is a feature
of the tool and a requirement of its tests.
"""

import pytest

from emberlog import LogFile
from emberlog.cli import main
from emberlog.clock import ENV_TODAY

TODAY = "2026-07-13"


@pytest.fixture(autouse=True)
def pinned_clock(monkeypatch):
    """Freeze the calendar for every test."""
    monkeypatch.setenv(ENV_TODAY, TODAY)


@pytest.fixture
def set_today(monkeypatch):
    """Move the frozen clock — the whole point of a TTL tool is time travel."""

    def _set(value: str) -> None:
        monkeypatch.setenv(ENV_TODAY, value)

    return _set


@pytest.fixture
def log_path(tmp_path):
    return str(tmp_path / "DECISIONS.md")


@pytest.fixture
def log(log_path):
    """A freshly initialized, empty log file on disk."""
    return LogFile.create(log_path)


@pytest.fixture
def run(capsys):
    """Invoke the CLI in-process; returns (exit_code, stdout, stderr)."""

    def _run(*argv: str):
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run
