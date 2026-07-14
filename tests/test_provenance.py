"""Provenance tag parsing: kind:name sources."""

import pytest

from emberlog.errors import ProvenanceError
from emberlog.provenance import KINDS, Source


def test_every_known_kind_parses_as_typed():
    for kind in KINDS:
        source = Source.parse(f"{kind}:someone")
        assert source.kind == kind
        assert source.is_typed
    # Names may carry their own structure (paths, URLs): only the first
    # colon splits, the rest belongs to the name.
    assert Source.parse("doc:docs/adr/0007-queue.md").name == "docs/adr/0007-queue.md"


def test_bare_name_parses_untyped():
    # Hand-edited files must never break outright; the linter flags these.
    source = Source.parse("alice")
    assert source.kind is None
    assert not source.is_typed


def test_unknown_kind_round_trips_but_is_untyped():
    source = Source.parse("oracle:delphi")
    assert source.kind == "oracle"
    assert not source.is_typed
    assert str(source) == "oracle:delphi"


def test_rejects_malformed_sources():
    for text in ("", "  ", "agent:", ":alice", "two words"):
        with pytest.raises(ProvenanceError):
            Source.parse(text)


def test_str_round_trip():
    for text in ("agent:claude-code", "human:alice", "bare"):
        assert str(Source.parse(text)) == text
