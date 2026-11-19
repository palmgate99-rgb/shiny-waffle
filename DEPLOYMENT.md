# Honest deployment status

## DXY proposal (disabled)

See [DXY_REVIEW.md](DXY_REVIEW.md) for source research, entitlement blockers,
the proposed private Barchart `$DXY` adapter and H1/H4 evidence board at `/dxy.html`.
This route is disabled, not live-verified, and has no continuous worker or external
notifications. TickerLayer index requests returned plan-denied 403; its USDX
catalog entry does not prove official ICE cash-index provenance or permissions.
The user approved code merge on 19 November 2026. Automatic Git deployments are
disabled in vercel.json. Do not enable DXY, deploy or activate notifications without
separate user approval and the documented provider acceptance checks.

This branch builds on PR #1, not main. The static monitoring dashboard displays saved Yahoo data. It is NOT a qualified trading-signal engine. No Eightcap account or execution integration exists.

## Existing Yahoo pipeline
Automatic public market-data publishing is DISABLED. The workflow only runs tests; it has read-only repository permission. Do not re-enable publication until provider redistribution rights are verified. The existing checked-in historical snapshot is not a live feed. A private backend/cache must replace the public JSON delivery path for live use. Yahoo is unofficial and not an Eightcap feed.

## Optional private TickerLayer adapter
`api/feed.js` is a Vercel Node handler, tested with mocks only. ChatGPT's existing TickerLayer connection is not a transferable deployment credential. Before enabling:
1. Confirm TickerLayer plan permits this use; no public redistribution without entitlement. See https://tickerlayer.com/terms-of-use.
2. Configure a private/authenticated deployment; never commit market payloads or keys publicly.
3. In deployment secrets set TICKERLAYER_API_KEY and DASHBOARD_ACCESS_TOKEN using user-approved credentials. Do not paste them into source, chat or URLs.
4. Authenticated GET /api/feed?pair=EURUSD requires Authorization: Bearer [private access token]. No public frontend hook is enabled yet. Never put the provider key in browser code.
5. Verify actual REST response schema, provider event timestamp, freshness and quota behavior before adapting the response into charts. observed_at is retrieval time, not event time. Current adapter supplies quotes, NOT historical candles or signals.

No server credential, provider entitlement, production access or successful live API deployment has been verified. Signal Whisper requested an upgrade in connector checks; ChartGaze was not exposed. Do not label these connected in the standalone dashboard. Qualified setups still require official event checks, COT, closed M15/H1 structure, TradingView corroboration and realistic cost-adjusted reward/risk. No success-rate claims.

Tests: python -m unittest fx_strategy.tests.test_strategy; node tests/dashboard.test.cjs; node tests/feed.test.cjs.

## Private frontend (new)
The separate Private TickerLayer panel calls the same-origin protected adapter, with the user's separate dashboard passphrase in an Authorization header. The provider key never reaches the browser. The passphrase remains in memory only; disconnect clears it. It refreshes at most once per minute per open tab. The backend caches each pair/timeframe in-process for 60 seconds (not a distributed quota guarantee).

The REST normalizer uses documented top-level bid/ask/timestamp in milliseconds and aggregate results o/h/l/c/t. It rejects malformed/future quotes, marks quotes older than 2 minutes stale, and removes forming candles. New private charts show actual closed candles separately from old Yahoo history; no strategy signal is inferred. This path has mock tests but still requires live authenticated verification after credential configuration and redeploy.
