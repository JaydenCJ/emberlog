# Decision Log

<!-- emberlog v1 -->

Read this file at the start of every session. It is kept honest by
`emberlog lint` — pin the clock with `EMBERLOG_TODAY=2026-08-01` to
reproduce the outputs shown in [`README.md`](README.md) exactly.

## Use SQLite for the job queue
<!-- ember id=6e28c8 added=2026-07-13 ttl=90d expires=2026-10-11 source=agent:claude-code confidence=observed tags=architecture,storage -->

Postgres was overkill for a single-writer queue; SQLite in WAL mode
handled 40x our peak write volume in the 2026-07-12 load test.

## Deploys happen from main only
<!-- ember id=b2ac04 added=2026-07-13 ttl=never source=human:alice confidence=verified tags=process -->

Release branches were retired in Q2. This is policy, not observation.

## Staging resets its database every Monday
<!-- ember id=3430c6 added=2026-06-01 ttl=45d expires=2026-07-16 source=doc:docs/runbook.md confidence=observed tags=infra -->

Anything seeded into staging on Friday is gone by the demo.

## The flaky checkout test is probably the shared cart fixture
<!-- ember id=812d9a added=2026-06-10 ttl=30d expires=2026-07-10 source=agent:claude-code confidence=guess tags=testing -->

Three of five failures touched the same fixture. Never confirmed.

## Payment provider sandbox rate limit is 60 rpm
<!-- ember id=e91125 added=2026-05-20 ttl=6m expires=2026-11-20 tags=integrations -->

Hit it twice during the spike; back off to 30 rpm in tests.
