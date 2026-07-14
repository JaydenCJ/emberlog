# emberlog examples

`DECISIONS.md` is a small but realistic project decision log: two healthy
entries, one policy pinned with `ttl=never`, and three kinds of rot —
an expired runbook fact, an expired 52-day-old guess, and an entry nobody
signed. Every id and `expires=` date in it was written by emberlog itself.

All commands below pin the clock so the output is reproducible forever:

```bash
export EMBERLOG_TODAY=2026-08-01
```

## Lint the log

```bash
emberlog lint -f examples/DECISIONS.md
```

```text
examples/DECISIONS.md:20: E101 expired: "Staging resets its database every Monday" expired 2026-07-16 (16d ago) — renew it, retire it, or run 'emberlog sweep'
examples/DECISIONS.md:25: E101 expired: "The flaky checkout test is probably the shared cart fixture" expired 2026-07-10 (22d ago) — renew it, retire it, or run 'emberlog sweep'
examples/DECISIONS.md:25: W205 stale-unverified: "The flaky checkout test is probably the shared cart fixture" is still confidence=guess after 52d — verify it or retire it
examples/DECISIONS.md:30: W203 no-provenance: "Payment provider sandbox rate limit is 60 rpm" has no source= — future readers cannot weigh it
examples/DECISIONS.md: 4 findings (2 errors, 2 warnings)
```

Exit code is 1 (errors present), so this slots straight into CI or a
pre-session hook. `--strict` makes the two warnings fail too.

## Clean it up

```bash
emberlog sweep -f examples/DECISIONS.md --dry-run   # preview, moves nothing
emberlog sweep -f examples/DECISIONS.md             # expired → DECISIONS.archive.md
emberlog verify -f examples/DECISIONS.md 812d9a     # if the guess was confirmed instead
emberlog renew -f examples/DECISIONS.md 3430c6      # if the fact still holds
```

The sweep is non-destructive: entries land in
`examples/DECISIONS.archive.md` with `status=expired swept=<date>`, so
history stays greppable while the working file stays trustworthy.
(Sweeping the example modifies the checked-in files — `git checkout` them
to reset the demo.)

## Wire it into an agent session

`session-start.sh` shows the intended integration: run it as the first
step of an agent's session (a Claude Code hook, a Makefile target, a
direnv hook) so the session refuses to trust a rotten log.

```bash
bash examples/session-start.sh examples/DECISIONS.md
```

It prints the lint report, then a compact table of what is still fresh —
exactly what you want pasted at the top of an agent's context.
