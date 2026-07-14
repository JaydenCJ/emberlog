"""Deterministic id derivation and validation."""

import datetime as dt

from emberlog.ids import ID_LENGTH, is_valid_id, new_id

ADDED = dt.date(2026, 7, 13)


def test_same_inputs_same_id_and_shape():
    # Determinism keeps docs, tests, and smoke output byte-stable.
    generated = new_id("Use SQLite", ADDED)
    assert generated == new_id("Use SQLite", ADDED)
    assert len(generated) == ID_LENGTH
    assert is_valid_id(generated)


def test_different_titles_different_ids():
    assert new_id("Use SQLite", ADDED) != new_id("Use Postgres", ADDED)


def test_collision_bumps_nonce():
    first = new_id("Use SQLite", ADDED)
    second = new_id("Use SQLite", ADDED, taken={first})
    assert second != first
    assert is_valid_id(second)


def test_is_valid_id_rejects_wrong_shapes():
    assert not is_valid_id("ABC123")  # uppercase
    assert not is_valid_id("abc12")  # too short
    assert not is_valid_id("ghijkl")  # not hex
    assert not is_valid_id("")
