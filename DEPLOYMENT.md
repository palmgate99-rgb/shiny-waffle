# Honest deployment status

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
