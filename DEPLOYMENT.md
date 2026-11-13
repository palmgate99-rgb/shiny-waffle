# Honest deployment status

This branch builds on PR #1, not main. The static monitoring dashboard displays saved Yahoo data. It is NOT a qualified trading-signal engine. No Eightcap account or execution integration exists.

## Existing Yahoo pipeline
Automatic public market-data publishing is DISABLED. The workflow only runs tests; it has read-only repository permission. Do not re-enable publication until provider redistribution rights are verified. The existing checked-in historical snapshot is not a live feed. A private backend/cache must replace the public JSON delivery path for live use. Yahoo is unofficial and not an Eightcap feed.

## Optional private TickerLayer adapter
`api/feed.js` is a Vercel Node handler, tested with mocks only. ChatGPT's existing TickerLayer connection is not a transferable deployment credential. Before enabling:
1. Confirm TickerLayer plan permits this use; no public redistribution without entitlement. See https://tickerlayer.com/terms-of-use.
2. Configure a private/authenticated deployment; never commit market payloads or keys publicly.
3. In deployment secrets set TICKERLAYER_API_KEY and DASHBOARD_ACCESS_TOKEN using user-approved credentials. Do not paste them into source, chat or URLs.
4. Authenticated GET /api/feed?pair=EURUSD requires Authorization: Bearer [private access token]. The private frontend sends this header after the user enters a separate passphrase. Never put the provider key in browser code.
5. Verify actual REST response schema, provider event timestamp, freshness and quota behavior before adapting the response into charts. observed_at is retrieval time, not event time. Current adapter supplies quotes and closed historical candles, not qualified signals.

Secrets were configured in Vercel and protected preview deployment verified READY, but provider entitlement and an authenticated live API response remain unverified. Signal Whisper requested an upgrade in connector checks; ChartGaze was not exposed. Do not label these connected in the standalone dashboard. Qualified setups still require official event checks, COT, closed M15/H1 structure, TradingView corroboration and realistic cost-adjusted reward/risk. No success-rate claims.

Tests: python -m unittest fx_strategy.tests.test_strategy; node tests/dashboard.test.cjs; node tests/feed.test.cjs.

## Private frontend (new)
The separate Private TickerLayer panel calls the same-origin protected adapter, with the user's separate dashboard passphrase in an Authorization header. The provider key never reaches the browser. The passphrase remains in memory only; disconnect clears it. Manual refresh is default, with optional one-minute quote updates while visible. The backend shares quote cache across timeframes and holds complete candles until the next close (not a distributed quota guarantee).

The REST normalizer uses documented top-level bid/ask/timestamp in milliseconds and aggregate results o/h/l/c/t. It rejects malformed/future quotes, marks quotes older than 2 minutes stale, and removes forming candles. New private charts show actual closed candles separately from old Yahoo history; no strategy signal is inferred. This path has mock tests but still requires live authenticated verification after credential configuration and redeploy.

## November 13 efficiency and signal-safety update
- Manual refresh is the default; optional one-minute automatic quotes pause in hidden tabs. Cached quote requests are shared across timeframes in one server instance; candle refresh is aligned to timeframe closes with short retry on incomplete data. Identical concurrent requests are deduplicated in that instance. Respect provider Retry-After and back off on failure.
- This is NOT a persistent distributed quota limiter: separate instances/tabs can consume more requests. A durable private quota store is not provisioned. Check the actual provider allowance before enabling sustained refresh; no paid services were added.
- Private history requests up to 300 completed bars over 28 calendar days. This is sufficient for displayed 20-bar context/RSI when returned, but not necessarily 200/252-bar H4 legacy rules. No synthetic history is filled.
- Selected private timeframe shows 20-bar mean/range, indicative spread, RSI(14) Wilder smoothing, CRT and price-action observations. CRT is explicitly: range candle, single-sided sweep closing back inside that range, third candle closes beyond the sweep candle opposite to the sweep. A two-sided sweep is rejected. Price action compares latest close with the previous 20 closed candles' extremes. These definitions are not universal or a validated edge.
- SMT requires synchronized paired-market data; it is deliberately unavailable rather than inferred from a single series. Multi-timeframe structure, official events, current dated CFTC, broker costs and realistic target checks remain blockers to any qualified signal. The five-check panel states each missing prerequisite; no TP/SL recommendation is fabricated.
- Old Yahoo scanner remains separately labeled historical research. Private data is not routed into incompatible legacy 200/252-bar rules. No broker connection, trade placement, subscription, public credential or public live-data publication is added.
- Validation uses mocks only. Actual authenticated response still requires private user login/passphrase; Vercel READY does not prove live market access. No new performance backtest or paper-trading evidence claimed.
