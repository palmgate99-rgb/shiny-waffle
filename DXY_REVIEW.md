# DXY integration proposal — 19 November 2026

Status: user approved code merge on 19 November 2026. Integration is NOT
live-verified, enabled, scheduled or connected to notifications. No real DXY price
was obtained in this inspection. The new API remains disabled by default.

## Source findings

| Route | Evidence | Decision |
| --- | --- | --- |
| ICE DXY cash index | ICE identifies DXY as its six-currency spot index; offers intraday, historical and real-time delivery | Authoritative source. Obtain a DXY-specific entitlement and delivery agreement; no account entitlement has been verified |
| Barchart OnDemand `$DXY` | Barchart publishes a `$DXY` index page and documents getQuote, getHistory and getInstrumentDefinition | Candidate adapter implemented behind gates; API coverage, official ICE provenance, interval support and account permissions remain unverified |
| TickerLayer `indices/USDX` | Authenticated catalog returned USDX with aggregates enabled; H1 previous-close and H4 history calls both returned 403, index plan missing | Unavailable on current connected account; terms describe derived indicative data, not official index data. No substitution |
| Yahoo / historical JSON | Saved historical dashboard data, not a continuously running authenticated feed | Excluded from DXY route |
| DX futures / broker USDX CFD / UUP ETF / Fed broad dollar index | Distinct instrument definitions and price processes | Never silently relabel as DXY cash index |

Sources inspected:

- https://developer.ice.com/fixed-income-data-services/catalog/ice-data-indices-currency-indices
- https://www.ice.com/fixed-income-data-services/access-and-delivery/connectivity-and-feeds/ice-consolidated-history
- https://www.ice.com/fixed-income-data-services/data-and-analytics/proprietary-data
- https://www.barchart.com/stocks/quotes/%24DXY/price-history
- https://www.barchart.com/ondemand/api/getHistory
- https://www.barchart.com/ondemand/api/getQuote
- https://www.barchart.com/ondemand/api/getInstrumentDefinition
- https://tickerlayer.com/terms-of-use (effective 15 November 2026)

ICE documents intraday OHLC history delivery. That does not prove that a particular
account can retrieve DXY H1/H4 candles. Barchart documents minute intervals, quote
event timestamps and real-time/delayed/EOD mode. Its API documentation was available
in search extracts; direct page opens returned a bot-verification page. Public
instrument pages and generic API docs do not establish this user's entitlement.
No subscription purchase, key transfer or licensing agreement was made.

## Proposed changes

- `api/dxy.js`: separate authenticated, read-only backend calling documented
  Barchart getQuote and getHistory POST endpoints for `$DXY`, 60/240 minutes.
  Fixed host and symbol; key in server-side form body, not browser or URL;
  redirects rejected; eight-second timeout; no provider error text or raw payload logs.
- `lib/dxy.cjs`: permission gate, quote/candle validation, confirmed swing analysis,
  conditional setup watches, DST-aware analysis windows and response expiry.
- `dxy.html`: separate observations, technical conditions, potential setups and
  session heads-ups; explicit one-shot check; memory-only dashboard passphrase;
  clears failures, disconnects and expired observations. Link from existing dashboard.
- Tests and CI test command. Fixtures are synthetic and confined to tests. No
  fetched prices, test candles or entitlement evidence are written into public JSON.
- Existing Yahoo exporter deliberately does not gain a DXY alias or fallback.

## Required verification before enabling

1. Ask ICE or Barchart for written coverage of **ICE DXY cash index**, real-time
   levels, historical intraday OHLC, internal automated analysis, authenticated
   private display, permitted retention and any intended derived session alerts.
   Public display and redistribution require separate permission where applicable.
   Identify the subscriber and actual plan. An MCP connection is not a server key.
2. Obtain the account-specific instrument definition. Confirm `$DXY` identifier,
   ICE provenance, cash index classification, quote/history identifier mappings,
   exchange/source code and units. Archive the definition and contract reference
   privately; compare them to independently licensed ICE observations. Reject
   futures/CFD/derived substitutes even if the display name says Dollar Index.
3. Retrieve authenticated quote, H1 and H4 responses in a private validation
   environment. Confirm status schema, numeric types, timezone offset, mode `R`,
   event timestamp meaning for this index, and real delay. `serverTimestamp` or
   retrieval time must never stand in for the price event time.
4. Verify history timestamps mean **bar start**; native 60/240 minute bars are full
   UTC-aligned buckets (H4 00/04/08/12/16/20 UTC), finalization delay and corrections.
   The current implementation only accepts that contract. Do not assert these
   semantics just to enable it. If the vendor uses another anchor, partial sessions
   or closing timestamps, adapt and test first, or aggregate licensed smaller bars
   with an explicitly verified calendar and completeness policy.
5. Reconcile provider holidays, publication breaks and weekend boundaries with
   the official **cash index** calendar, separately from DX futures hours. Current
   code deliberately rejects every gap in the returned closed-candle window;
   legitimate breaks can therefore block analysis. Calendar-aware gap handling is
   still required for reliable service. Never fill missing bars with invented OHLC.
6. Verify clock synchronization, quotas, 403/429 responses, outages, delayed mode,
   close-boundary behavior and absence of credentials in logs. Complete a private
   live acceptance run and record evidence separately from deterministic CI tests.

Only then populate server secrets: `BARCHART_API_KEY`, `DASHBOARD_ACCESS_TOKEN`,
and `DXY_PERMISSION_RECORD`. The permission record must contain:

| Field | Required value / meaning |
| --- | --- |
| provider | `Barchart OnDemand` |
| symbol | `$DXY` |
| instrument | `ICE DXY cash index` |
| use | `private_display_and_analysis` |
| realtime, history | Boolean true after account-specific verification |
| timestamp_semantics | `bar_start` after verification |
| utc_aligned_full_bars | Boolean true after verification |
| evidence_ref | Nonempty private reference to contract, metadata and live acceptance evidence |
| verified_at | Offset-qualified ISO timestamp, no more than 30 days old |
| expires_at | Offset-qualified ISO timestamp; no later than entitlement expiry |

This administrative record is an attestation, not an automated license check or
proof of provider authenticity. It is not returned to the browser. Runtime still
checks every returned symbol, mode, timestamp and candle. Setting `DXY_ENABLED=true`
is a separate activation step, requiring user approval. Never commit credentials or
the actual private permission record. No placeholder permission file is supplied.

## Data and analysis rules

- Reject quote event age over 120 seconds, future timestamps, missing offsets,
  non-real-time mode, wrong symbol and nonpositive/nonfinite values.
- Exclude forming candles and bars closed less than 120 seconds ago. Require the
  most recently due UTC candle, at least 12 closed bars per timeframe, correct OHLC,
  unique starts and no gaps. All analysis is withheld if either timeframe fails.
  The conservative wall-clock rule also rejects closures; no stale weekend signal.
- Confirm swing highs/lows with two closed bars on each side. Bullish requires
  higher confirmed highs and lows; bearish requires lower highs and lows; otherwise
  range or undetermined. Confirmation times are disclosed. These are deterministic
  technical conditions, not proof of institutional order flow, SMC or CRT.
- A watch is eligible only when H1/H4 direction agrees and the latest H1 close is
  beyond its confirmed swing in that direction. It requests a later closed-H1 retest;
  it is not an entry alert. Prior swing supplies a structural invalidation reference.
  Entry, TP and SL remain null pending executable-instrument, event-risk, retest,
  broker-cost and reward/risk checks. No performance or win-rate claim.
- Response expires at the earlier of quote freshness deadline or next due candle
  finalization. UI clears it automatically. Provider retrieval time is separate.
- Session planning conventions: Asia 09:00–17:00 Tokyo; London 08:00–16:00 London;
  New York 08:00–17:00 New York. Heads-up window is 30 minutes before each opening.
  IANA timezones handle DST, including transition weeks. Windows can overlap;
  they do not assert exchange or holiday status. This page only checks on request.

## Infrastructure needed for reliable alerts (not activated)

An always-available private worker, provider-approved polling or streaming, a
licensed historical backfill store and a verified cash-index calendar are needed.
Use a shared cache and rate limiter; three provider requests per page check here
are intentionally not a production quota-control solution. Authenticate the whole
deployment, apply access limits, and manage rotating secrets with a server secret
manager. Do not publish market payloads in repository files or static build artifacts.

Run H1/H4 jobs after confirmed finalization and session jobs using the listed IANA
zones. Validate quote freshness at dispatch, not merely at ingestion. Store candle
versions, data provenance, last successful check, stale reasons and revisions.
Use a durable queue/outbox and an atomic uniqueness key such as provider + index +
session date + timeframe + last closed bar + condition + direction. Add retry
backoff, delivery receipts, duplicate suppression, restart recovery and a kill
switch. Suppress market messages on stale/invalid inputs; route operational outage
notices separately. Clock drift and missed jobs need health checks and observability.

External notifications additionally require approval of channel, recipient,
session windows, frequency, message content, credentials and provider permission
for derived alerts. ChatGPT hourly scheduled checks alone do not guarantee timely
bar-close or 30-minute pre-session delivery. No automation, notification, agent
daemon, trade execution or subscription upgrade was created by this change.

## Review and rollout

Changes originated on `review/dxy-official-data-gates`, based on PR #2 head
`cc9685113551111b0aad66339d0d66d98bd392bb`. The user subsequently approved merging
the reviewed code. PR #2 retains its development-branch target; this does not merge
the dashboard into `main`. Connected Vercel checks were observed on the old head.
`vercel.json` therefore sets `git.deploymentEnabled=false` to prevent automatic Git
deployments while merging. Deployment and external notifications still require
separate approval. Provider acceptance and calendar work remain technical blockers.
Deterministic tests do not establish live data availability or legal permission.
Browser rendering has not been verified.

Local validation completed: 19 existing Python strategy tests; existing dashboard,
feed and private-UI Node suites; 11 new DXY backend/analysis/UI tests. All passed.
New tests cover rejection and expiry, closed-bar finalization, confirmed swings,
DST session windows, conditional watches, fixed POST destinations, credential
isolation and clearing all observations on provider failure. These use test
fixtures, not live market prices. GitHub CI must pass on the updated PR head before
merge. No manual hosting deployment is part of this change.
