"""Lint rules: each rule fires when it should and stays quiet otherwise."""

import datetime as dt
import textwrap

from emberlog.lint import LintOptions, lint_document, summarize
from emberlog.parser import parse_document

TODAY = dt.date(2026, 7, 13)


def lint_text(text: str, today: dt.date = TODAY, **options) -> list:
    doc = parse_document(textwrap.dedent(text).lstrip("\n"))
    return lint_document(doc, today, LintOptions(**options) if options else None)


def codes(text: str, today: dt.date = TODAY, **options) -> list:
    return [finding.code for finding in lint_text(text, today, **options)]


HEALTHY = """
    <!-- emberlog v1 -->

    ## Healthy entry
    <!-- ember id=aaaaaa added=2026-07-01 ttl=90d source=human:alice confidence=verified -->
"""


def test_healthy_log_is_clean():
    assert codes(HEALTHY) == []
    # ttl=never is an intentional statement, not missing hygiene.
    assert codes(HEALTHY.replace("ttl=90d", "ttl=never")) == []


def test_e101_expired_entry(log):
    entry = log.add("Rots fast", ttl="7d", source="human:alice", today=TODAY)
    findings = lint_document(log.doc, dt.date(2026, 8, 1))
    assert [f.code for f in findings] == ["E101"]
    assert findings[0].entry_id == entry.id
    assert "expired 2026-07-20" in findings[0].message


def test_e101_boundary_expiry_day_is_not_expired(log):
    # An entry is stale strictly *after* its expiry date, not on it: on the
    # day itself it is still (barely) live and warns instead of failing.
    log.add("Edge", ttl="7d", source="human:alice", today=TODAY)
    on_the_day = lint_document(log.doc, dt.date(2026, 7, 20))
    assert [f.code for f in on_the_day] == ["W201"]
    day_after = lint_document(log.doc, dt.date(2026, 7, 21))
    assert [f.code for f in day_after] == ["E101"]


def test_w201_expiring_soon_respects_horizon(log):
    log.add("Soonish", ttl="30d", source="human:alice", today=TODAY)
    on_horizon = dt.date(2026, 7, 29)  # 14 days before 2026-08-12
    assert [f.code for f in lint_document(log.doc, on_horizon)] == ["W201"]
    assert lint_document(log.doc, dt.date(2026, 7, 28)) == []
    # A wider horizon pulls the warning earlier.
    wide = lint_document(log.doc, dt.date(2026, 7, 14), LintOptions(horizon_days=60))
    assert [f.code for f in wide] == ["W201"]


def test_w202_missing_ttl():
    assert (
        codes(
            """
            <!-- emberlog v1 -->

            ## Unbounded
            <!-- ember id=aaaaaa added=2026-07-01 source=human:alice -->
            """
        )
        == ["W202"]
    )


def test_w203_missing_provenance():
    assert (
        codes(
            """
            <!-- emberlog v1 -->

            ## Anonymous
            <!-- ember id=aaaaaa added=2026-07-01 ttl=90d -->
            """
        )
        == ["W203"]
    )


def test_w204_untyped_and_unknown_kinds():
    findings = lint_text(
        """
        <!-- emberlog v1 -->

        ## Bare
        <!-- ember id=aaaaaa added=2026-07-01 ttl=90d source=alice -->

        ## Unknown kind
        <!-- ember id=bbbbbb added=2026-07-01 ttl=90d source=oracle:delphi -->
        """
    )
    assert [f.code for f in findings] == ["W204", "W204"]
    assert "no kind: prefix" in findings[0].message
    assert "unknown kind 'oracle'" in findings[1].message


def test_w205_stale_low_confidence_decays(log):
    entry = log.add(
        "Probably the cache",
        ttl="1y",
        source="agent:claude-code",
        confidence="guess",
        today=TODAY,
    )
    fresh = lint_document(log.doc, TODAY + dt.timedelta(days=45))
    assert fresh == []  # exactly at the decay age is still fine
    stale = lint_document(log.doc, TODAY + dt.timedelta(days=46))
    assert [f.code for f in stale] == ["W205"]
    # Verifying resets the decay clock via checked=.
    log.verify(entry.id, today=TODAY + dt.timedelta(days=46))
    assert lint_document(log.doc, TODAY + dt.timedelta(days=46)) == []


def test_e105_hand_edited_expires_drift():
    findings = lint_text(
        """
        <!-- emberlog v1 -->

        ## Drifted
        <!-- ember id=aaaaaa added=2026-07-01 ttl=30d expires=2026-12-25 source=human:alice confidence=verified -->

        ## Contradiction
        <!-- ember id=bbbbbb added=2026-07-01 ttl=never expires=2026-12-25 source=human:alice confidence=verified -->
        """
    )
    assert [f.code for f in findings] == ["E105", "E105"]
    assert "2026-07-31" in findings[0].message  # the correct computed date
    assert "no finite ttl" in findings[1].message


def test_e102_e103_e104_flow_from_parser_diagnostics():
    findings = lint_text(
        """
        <!-- emberlog v1 -->

        ## No metadata at all

        ## Bad field
        <!-- ember id=aaaaaa added=2026-07-01 ttl=soon source=human:alice confidence=verified -->

        ## Duplicate
        <!-- ember id=aaaaaa added=2026-07-01 ttl=90d source=human:alice confidence=verified -->
        """
    )
    assert [f.code for f in findings] == ["E102", "E104", "E103"]


def test_archived_entries_are_exempt_from_freshness_rules():
    # Archive files hold expired history on purpose; only date consistency
    # (E105) still applies there.
    assert (
        codes(
            """
            <!-- emberlog v1 -->

            ## Long dead
            <!-- ember id=aaaaaa added=2025-01-01 ttl=7d status=expired swept=2025-02-01 -->
            """
        )
        == []
    )


def test_findings_sort_by_line_then_code(log):
    log.add("No source, no ttl", today=TODAY)
    findings = lint_document(log.doc, TODAY)
    assert [f.code for f in findings] == ["W202", "W203"]


def test_summarize_and_render():
    findings = lint_text(
        """
        <!-- emberlog v1 -->

        ## Expired and anonymous
        <!-- ember id=aaaaaa added=2026-01-01 ttl=7d -->
        """
    )
    assert summarize(findings) == (1, 1)  # E101 expired + W203 no-provenance
    rendered = findings[0].render("DECISIONS.md")
    assert rendered == f"DECISIONS.md:{findings[0].line}: E101 expired: {findings[0].message}"
