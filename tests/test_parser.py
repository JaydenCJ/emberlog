"""Parser behavior: tolerant, lossless, diagnostic-collecting."""

import datetime as dt
import textwrap

import pytest

from emberlog.errors import NotEmberlogFileError
from emberlog.parser import RawBlock, parse_attrs, parse_document
from emberlog.ttl import Ttl


def doc_text(body: str) -> str:
    return textwrap.dedent(body).lstrip("\n")


MINIMAL = doc_text(
    """
    # Decision Log

    <!-- emberlog v1 -->

    ## Use SQLite for the job queue
    <!-- ember id=3f9c21 added=2026-07-13 ttl=90d source=agent:claude-code confidence=observed tags=Storage,storage,arch -->

    Postgres was overkill for a single-writer queue.
    """
)


def test_minimal_document_parses():
    doc = parse_document(MINIMAL)
    assert doc.title == "Decision Log"
    assert doc.diagnostics == []
    (entry,) = doc.entries
    assert entry.id == "3f9c21"
    assert entry.added == dt.date(2026, 7, 13)
    assert entry.ttl == Ttl(90, "d")
    assert str(entry.source) == "agent:claude-code"
    assert entry.confidence == "observed"
    assert entry.body == "Postgres was overkill for a single-writer queue."
    assert entry.line == 5  # heading line, 1-based
    assert entry.tags == ("storage", "arch")  # lowercased, deduplicated


def test_missing_marker_raises_and_h1_defaults():
    with pytest.raises(NotEmberlogFileError):
        parse_document("# Notes\n\n## Something\n", path="NOTES.md")
    headerless = parse_document("<!-- emberlog v1 -->\n")
    assert headerless.title == "Decision Log"
    assert headerless.entries == []


def test_preamble_prose_is_preserved():
    text = doc_text(
        """
        # Log

        <!-- emberlog v1 -->

        Read this file at session start.
        It is linted by emberlog.

        ## First
        <!-- ember id=aaaaaa added=2026-07-01 -->
        """
    )
    doc = parse_document(text)
    assert doc.preamble == "Read this file at session start.\nIt is linted by emberlog."


def test_multiline_body_with_markdown_survives():
    text = doc_text(
        """
        <!-- emberlog v1 -->

        ## Entry
        <!-- ember id=aaaaaa added=2026-07-01 -->

        First paragraph.

        - a list item
        - `code` too

        Second paragraph.
        """
    )
    (entry,) = parse_document(text).entries
    assert entry.body.startswith("First paragraph.")
    assert "- a list item" in entry.body
    assert entry.body.endswith("Second paragraph.")


def test_block_without_ember_comment_becomes_raw():
    text = doc_text(
        """
        <!-- emberlog v1 -->

        ## Just a heading someone typed

        With prose but no metadata.
        """
    )
    doc = parse_document(text)
    assert doc.entries == []
    (node,) = doc.nodes
    assert isinstance(node, RawBlock)
    assert "no <!-- ember" in doc.diagnostics[0].message
    assert doc.diagnostics[0].code == "malformed"


def test_broken_required_fields_become_raw_blocks():
    # Without an id there is no way to address the entry; without a valid
    # anchor date no expiry math is possible. Either way the whole block is
    # preserved verbatim rather than half-interpreted.
    text = doc_text(
        """
        <!-- emberlog v1 -->

        ## No id here
        <!-- ember added=2026-07-01 ttl=30d -->

        ## Bad date
        <!-- ember id=aaaaaa added=07/01/2026 -->
        """
    )
    doc = parse_document(text)
    assert doc.entries == []
    assert all(isinstance(node, RawBlock) for node in doc.nodes)
    assert "no id=" in doc.diagnostics[0].message
    assert "07/01/2026" in doc.nodes[1].text


def test_bad_ttl_keeps_entry_and_flags_field():
    text = doc_text(
        """
        <!-- emberlog v1 -->

        ## Bad ttl
        <!-- ember id=aaaaaa added=2026-07-01 ttl=fortnight -->
        """
    )
    doc = parse_document(text)
    (entry,) = doc.entries
    assert entry.ttl is None
    assert entry.invalid == {"ttl": "fortnight"}
    assert doc.diagnostics[0].code == "bad-field"


def test_unknown_keys_land_in_extras():
    text = doc_text(
        """
        <!-- emberlog v1 -->

        ## Forward compatible
        <!-- ember id=aaaaaa added=2026-07-01 priority=high owner=platform -->
        """
    )
    (entry,) = parse_document(text).entries
    assert entry.extras == {"priority": "high", "owner": "platform"}


def test_duplicate_ids_are_flagged_but_both_kept():
    text = doc_text(
        """
        <!-- emberlog v1 -->

        ## First
        <!-- ember id=aaaaaa added=2026-07-01 -->

        ## Second
        <!-- ember id=aaaaaa added=2026-07-02 -->
        """
    )
    doc = parse_document(text)
    assert len(doc.entries) == 2
    codes = [d.code for d in doc.diagnostics]
    assert codes == ["duplicate-id"]


def test_quoted_values_with_spaces_and_escapes():
    text = doc_text(
        """
        <!-- emberlog v1 -->

        ## Retired one
        <!-- ember id=aaaaaa added=2026-07-01 status=retired reason="superseded by ADR-7" -->
        """
    )
    (entry,) = parse_document(text).entries
    assert entry.status == "retired"
    assert entry.reason == "superseded by ADR-7"
    attrs, clean = parse_attrs(' reason="say \\"no\\" twice" ttl=30d ')
    assert clean
    assert attrs == {"reason": 'say "no" twice', "ttl": "30d"}


def test_crlf_input_parses():
    doc = parse_document(MINIMAL.replace("\n", "\r\n"))
    assert len(doc.entries) == 1
    assert doc.diagnostics == []


def test_ember_comment_may_wrap_lines():
    text = doc_text(
        """
        <!-- emberlog v1 -->

        ## Wrapped
        <!-- ember id=aaaaaa added=2026-07-01 ttl=30d
             source=human:alice confidence=verified -->
        """
    )
    (entry,) = parse_document(text).entries
    assert str(entry.source) == "human:alice"
    assert entry.confidence == "verified"


def test_stray_tokens_make_block_raw():
    # Junk between pairs could be a mangled edit; preserve, do not guess.
    text = doc_text(
        """
        <!-- emberlog v1 -->

        ## Stray
        <!-- ember id=aaaaaa added=2026-07-01 oops ttl=30d -->
        """
    )
    doc = parse_document(text)
    assert doc.entries == []
    assert "stray or repeated" in doc.diagnostics[0].message
