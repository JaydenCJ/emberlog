"""LogFile operations: the full entry lifecycle against real files."""

import datetime as dt
import os

import pytest

from emberlog import LogFile, default_archive_path
from emberlog.errors import (
    AmbiguousIdError,
    DuplicateIdError,
    EntryNotFoundError,
    FieldError,
)

TODAY = dt.date(2026, 7, 13)
LATER = dt.date(2026, 9, 1)


def test_create_refuses_to_overwrite(log, log_path):
    with pytest.raises(FieldError):
        LogFile.create(log_path)


def test_add_save_load_round_trip(log, log_path):
    log.add(
        "Use SQLite for the job queue",
        ttl="90d",
        source="agent:claude-code",
        confidence="observed",
        tags=["storage"],
        body="Postgres was overkill.",
        today=TODAY,
    )
    log.save()
    reloaded = LogFile.load(log_path)
    (entry,) = reloaded.entries
    assert entry.title == "Use SQLite for the job queue"
    assert entry.expires == dt.date(2026, 10, 11)
    assert entry.body == "Postgres was overkill."


def test_add_same_title_same_day_gets_distinct_ids(log):
    first = log.add("Same claim", today=TODAY)
    second = log.add("Same claim", today=TODAY)
    assert first.id != second.id


def test_add_normalizes_title_whitespace(log):
    entry = log.add("  spaced \t out\ntitle ", today=TODAY)
    assert entry.title == "spaced out title"


def test_add_validates_title_confidence_and_id(log):
    with pytest.raises(FieldError):
        log.add("   ", today=TODAY)
    with pytest.raises(FieldError):
        log.add("ok", confidence="certain", today=TODAY)
    log.add("First", entry_id="abc123", today=TODAY)
    with pytest.raises(DuplicateIdError):
        log.add("Second", entry_id="abc123", today=TODAY)


def test_find_by_prefix_with_specific_errors(log):
    one = log.add("One", entry_id="abc111", today=TODAY)
    log.add("Two", entry_id="abc222", today=TODAY)
    assert log.find("abc1") is one
    assert log.find("ABC111") is one  # ids compare case-insensitively
    with pytest.raises(EntryNotFoundError):
        log.find("ffffff")
    with pytest.raises(AmbiguousIdError):
        log.find("abc")


def test_renew_re_anchors_expiry(log):
    entry = log.add("Renewable", ttl="30d", today=TODAY)
    assert entry.expires == dt.date(2026, 8, 12)
    log.renew(entry.id, today=LATER)
    assert entry.renewed == LATER
    assert entry.expires == dt.date(2026, 10, 1)  # 30d from Sep 1


def test_renew_can_change_ttl_but_requires_one(log):
    entry = log.add("No ttl yet", today=TODAY)
    with pytest.raises(FieldError):
        log.renew(entry.id, today=LATER)
    log.renew(entry.id, ttl="1w", today=LATER)
    assert entry.expires == dt.date(2026, 9, 8)


def test_verify_dates_the_check_but_keeps_expiry(log):
    # Verifying says "true today", not "true for another 90 days".
    entry = log.add("Verifiable", ttl="90d", confidence="guess", today=TODAY)
    log.verify(entry.id, today=LATER)
    assert entry.confidence == "verified"
    assert entry.checked == LATER
    assert entry.expires == dt.date(2026, 10, 11)  # unchanged anchor


def test_retire_moves_entry_to_archive_with_reason(log, log_path):
    entry = log.add("Wrong turn", ttl="90d", today=TODAY)
    keeper = log.add("Still true", ttl="90d", today=TODAY)
    log.retire(entry.id, reason="superseded by ADR-7", today=LATER)

    reloaded = LogFile.load(log_path)
    assert [e.id for e in reloaded.entries] == [keeper.id]

    archive = LogFile.load(default_archive_path(log_path))
    (archived,) = archive.entries
    assert archived.status == "retired"
    assert archived.reason == "superseded by ADR-7"
    assert archived.swept == LATER


def test_sweep_moves_only_expired_entries(log, log_path):
    stale = log.add("Short-lived", ttl="7d", today=TODAY)
    fresh = log.add("Long-lived", ttl="1y", today=TODAY)
    constant = log.add("Deploys happen from main only", ttl="never", today=TODAY)
    swept = log.sweep(today=LATER)
    assert [e.id for e in swept] == [stale.id]

    reloaded = LogFile.load(log_path)
    assert [e.id for e in reloaded.entries] == [fresh.id, constant.id]
    archive = LogFile.load(default_archive_path(log_path))
    assert archive.entries[0].status == "expired"
    # never-TTL entries survive any amount of time travel
    far_future = log.sweep(today=dt.date(2036, 1, 1), dry_run=True)
    assert constant.id not in [e.id for e in far_future]


def test_sweep_dry_run_touches_nothing(log, log_path):
    log.add("Short-lived", ttl="7d", today=TODAY)
    log.save()
    before = open(log_path, encoding="utf-8").read()
    swept = LogFile.load(log_path).sweep(today=LATER, dry_run=True)
    assert len(swept) == 1
    assert open(log_path, encoding="utf-8").read() == before
    assert not os.path.exists(default_archive_path(log_path))


def test_sweep_appends_to_existing_archive(log, log_path):
    log.add("First to rot", ttl="7d", today=TODAY)
    log.sweep(today=dt.date(2026, 8, 1))
    log.add("Second to rot", ttl="7d", today=dt.date(2026, 8, 1))
    log.sweep(today=LATER)
    archive = LogFile.load(default_archive_path(log_path))
    assert len(archive.entries) == 2


def test_stats_aggregates(log):
    log.add("Old guess", ttl="7d", confidence="guess", today=TODAY)  # expired
    log.add("Fresh", ttl="1y", source="human:alice", confidence="verified", today=LATER)
    log.add("Unbounded", source="somebody", today=LATER)  # no ttl, untyped
    stats = log.stats(today=LATER)
    assert stats.total == 3
    assert stats.expired == 1
    assert stats.no_ttl == 1
    assert stats.by_confidence == {"guess": 1, "verified": 1, "unset": 1}
    assert stats.by_source_kind == {"none": 1, "human": 1, "untyped": 1}
    assert stats.oldest is not None and stats.oldest.title == "Old guess"
    assert stats.next_expiry is not None and stats.next_expiry.title == "Fresh"


def test_default_archive_path_shapes():
    assert default_archive_path("DECISIONS.md") == "DECISIONS.archive.md"
    assert default_archive_path("notes/log.markdown") == "notes/log.archive.markdown"
