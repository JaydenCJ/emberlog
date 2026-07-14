"""Serialization: canonical form, healing, and lossless round-trips."""

import datetime as dt
import os
import textwrap

from emberlog.model import Entry
from emberlog.parser import parse_document
from emberlog.ttl import Ttl
from emberlog.writer import render_document, render_entry, write_document


def make_entry(**overrides) -> Entry:
    defaults = dict(
        title="Use SQLite",
        id="3f9c21",
        added=dt.date(2026, 7, 13),
        ttl=Ttl.parse("90d"),
    )
    defaults.update(overrides)
    return Entry(**defaults)


def test_render_entry_canonical_key_order():
    entry = make_entry(tags=("storage",), confidence="observed")
    rendered = render_entry(entry)
    assert rendered.splitlines()[1] == (
        "<!-- ember id=3f9c21 added=2026-07-13 ttl=90d expires=2026-10-11 "
        "confidence=observed tags=storage -->"
    )
    # Unknown keys trail the known ones, sorted, for stable diffs.
    extra = render_entry(make_entry(extras={"zeta": "1", "alpha": "2"}))
    assert extra.index("alpha=2") < extra.index("zeta=1")


def test_render_recomputes_drifted_expires():
    # A hand-edited (wrong) expires= is healed on the next save.
    text = textwrap.dedent(
        """
        <!-- emberlog v1 -->

        ## Drifted
        <!-- ember id=aaaaaa added=2026-07-01 ttl=30d expires=2026-12-25 -->
        """
    ).lstrip("\n")
    doc = parse_document(text)
    assert "expires=2026-07-31" in render_document(doc)
    assert "2026-12-25" not in render_document(doc)


def test_values_with_spaces_are_quoted_and_round_trip():
    entry = make_entry(status="retired", reason='superseded, see "ADR-7"')
    rendered = render_entry(entry)
    assert 'reason="superseded, see \\"ADR-7\\""' in rendered
    document = f"<!-- emberlog v1 -->\n\n{rendered}\n"
    (reparsed,) = parse_document(document).entries
    assert reparsed.reason == 'superseded, see "ADR-7"'


def test_render_parse_render_is_a_fixed_point():
    doc = parse_document(
        "<!-- emberlog v1 -->\n\n## A\n<!-- ember id=aaaaaa added=2026-07-01 "
        'ttl=30d source=human:alice tags=x,y reason="two words" zeta=1 -->\n\nBody.\n'
    )
    once = render_document(doc)
    twice = render_document(parse_document(once))
    assert once == twice


def test_raw_blocks_render_verbatim():
    text = textwrap.dedent(
        """
        <!-- emberlog v1 -->

        ## Human scribble

        no metadata here, just prose
        """
    ).lstrip("\n")
    rendered = render_document(parse_document(text))
    assert "## Human scribble" in rendered
    assert "no metadata here, just prose" in rendered


def test_invalid_field_values_are_re_emitted_verbatim():
    # A typo like ttl=fortnight must survive saves so nobody's intent is lost.
    text = (
        "<!-- emberlog v1 -->\n\n## Typo\n"
        "<!-- ember id=aaaaaa added=2026-07-01 ttl=fortnight -->\n"
    )
    rendered = render_document(parse_document(text))
    assert "ttl=fortnight" in rendered


def test_write_document_writes_atomically(tmp_path):
    path = tmp_path / "DECISIONS.md"
    doc = parse_document("<!-- emberlog v1 -->\n")
    doc.nodes.append(make_entry())
    write_document(str(path), doc)
    content = path.read_text(encoding="utf-8")
    assert content.endswith("\n")
    assert "id=3f9c21" in content
    # No temp files left behind next to the target.
    leftovers = [name for name in os.listdir(tmp_path) if name != "DECISIONS.md"]
    assert leftovers == []
