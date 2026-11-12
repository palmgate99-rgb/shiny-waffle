// Private server-to-server adapter. Never expose provider keys to the browser.
// Configure a private deployment and confirm provider entitlement before use.
const {timingSafeEqual} = require('node:crypto');
const PAIRS = new Set(['EURUSD','GBPUSD','USDJPY','USDCAD','USDCHF','AUDUSD','NZDUSD']);
module.exports = async function handler(req, res) {
  res.setHeader('Cache-Control', 'private, no-store');
  const secret = process.env.DASHBOARD_ACCESS_TOKEN;
  const key = process.env.TICKERLAYER_API_KEY;
  if (!secret || !key) return res.status(503).json({status:'not_connected',message:'Private access and provider credentials must be configured.'});
  const expected = Buffer.from(`Bearer ${secret}`);
  const actual = Buffer.from(req.headers.authorization || '');
  if (actual.length !== expected.length || !timingSafeEqual(actual,expected)) return res.status(401).json({status:'unauthorized'});
  if (req.method !== 'GET') return res.status(405).json({status:'method_not_allowed'});
  const pair = String(req.query.pair || 'EURUSD').toUpperCase();
  if (!PAIRS.has(pair)) return res.status(400).json({status:'unsupported_pair'});
  try {
    const response = await fetch(`https://api.tickerlayer.com/forex/quote/${pair}`, {
      headers:{'x-api-key':key},signal:AbortSignal.timeout(8000)
    });
    if (!response.ok) return res.status(response.status === 429 ? 429 : 502).json({status:'provider_unavailable',provider_status:response.status});
    const quote = await response.json();
    return res.status(200).json({status:'indicative_quote_only',provider:'TickerLayer',pair,observed_at:new Date().toISOString(),quote,
      notice:'Observation time is not quote event time. No trading signal or broker execution quote.'});
  } catch (_) {
    return res.status(502).json({status:'provider_unavailable'});
  }
};
