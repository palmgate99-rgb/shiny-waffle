// Official cash-index path only. No TickerLayer/Yahoo/futures fallback.
const HOUR = 3600000, GRACE = 120000;
function fail(code) { throw Object.assign(new Error(code), {code}); }
function timestamp(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) fail('invalid_timestamp');
  const t = Date.parse(value);
  if (!Number.isFinite(t)) fail('invalid_timestamp');
  return t;
}
function permissions(raw, now) {
  let p; try { p = JSON.parse(raw); } catch { fail('entitlement_unverified'); }
  if (!p || p.provider !== 'Barchart OnDemand' || p.symbol !== '$DXY' ||
      p.instrument !== 'ICE DXY cash index' || p.use !== 'private_display_and_analysis' ||
      p.realtime !== true || p.history !== true || p.timestamp_semantics !== 'bar_start' ||
      p.utc_aligned_full_bars !== true || typeof p.evidence_ref !== 'string' || !p.evidence_ref.trim() ||
      !Number.isFinite(timestamp(p.expires_at)) || timestamp(p.expires_at) <= now ||
      timestamp(p.verified_at) > now || now - timestamp(p.verified_at) > 30*86400000) fail('entitlement_unverified');
  return p;
}
function results(body) {
  if (body?.status?.code !== 200 || !Array.isArray(body.results)) fail('provider_rejected');
  return body.results;
}
function quote(body, now) {
  const rows = results(body), q = rows[0];
  if (rows.length !== 1 || q?.symbol !== '$DXY' || typeof q.mode !== 'string' ||
      q.mode.toUpperCase() !== 'R' || !Number.isFinite(q.lastPrice) || q.lastPrice <= 0) fail('invalid_quote');
  const event = timestamp(q.tradeTimestamp);
  if (event > now || now-event > GRACE) fail('stale_quote');
  return {value:q.lastPrice,event_at:new Date(event).toISOString(),age_ms:now-event,mode:'real_time'};
}
function bars(body, hours, now) {
  const duration = hours*HOUR, seen = new Set();
  const all = results(body).map(b => {
    const start = timestamp(b.timestamp);
    if (b.symbol !== '$DXY' || ![b.open,b.high,b.low,b.close].every(Number.isFinite) ||
        Math.min(b.open,b.high,b.low,b.close) <= 0 || b.high < Math.max(b.open,b.close,b.low) ||
        b.low > Math.min(b.open,b.close,b.high) || start % duration !== 0 || seen.has(start) || start > now) fail('invalid_candle');
    seen.add(start);
    return {start_ms:start,end_ms:start+duration,open:b.open,high:b.high,low:b.low,close:b.close};
  }).sort((a,b)=>a.start_ms-b.start_ms);
  // A forming bar is never used. Allow two minutes for provider finalization.
  const closed = all.filter(b=>b.end_ms+GRACE<=now).slice(-120);
  const expectedEnd = Math.floor((now-GRACE)/duration)*duration;
  if (closed.length < 12) fail('insufficient_history');
  if (closed.at(-1).end_ms !== expectedEnd) fail('stale_candles');
  // Strict until a provider calendar is verified: gaps suppress analysis, even at closures.
  if (closed.some((b,i)=>i && b.start_ms !== closed[i-1].end_ms)) fail('candle_gap');
  return closed;
}
function structure(candles) {
  const highs=[], lows=[];
  // Two bars on each side confirm each swing; no lookahead beyond closed observations.
  for (let i=2;i<candles.length-2;i++) {
    const b=candles[i], others=candles.slice(i-2,i+3).filter((_,j)=>j!==2);
    if (others.every(x=>b.high>x.high)) highs.push({level:b.high,at:b.start_ms,confirmed_at:candles[i+2].end_ms});
    if (others.every(x=>b.low<x.low)) lows.push({level:b.low,at:b.start_ms,confirmed_at:candles[i+2].end_ms});
  }
  const h=highs.at(-1), l=lows.at(-1), close=candles.at(-1).close;
  let direction='undetermined';
  if (highs.length>=2 && lows.length>=2) {
    direction=h.level>highs.at(-2).level && l.level>lows.at(-2).level?'bullish':
      h.level<highs.at(-2).level && l.level<lows.at(-2).level?'bearish':'range';
  }
  return {direction,last_confirmed_high:h??null,last_confirmed_low:l??null,
    close_above_swing_high:!!h && close>h.level,close_below_swing_low:!!l && close<l.level,
    last_closed_at:new Date(candles.at(-1).end_ms).toISOString()};
}
function sessions(now) {
  const windows=[['Asia','Asia/Tokyo',9,17],['London','Europe/London',8,16],['New York','America/New_York',8,17]];
  return windows.map(([name,zone,start,end])=>{
    const parts=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:zone,weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(now).map(p=>[p.type,p.value]));
    const minute=Number(parts.hour)*60+Number(parts.minute), weekday=!['Sat','Sun'].includes(parts.weekday);
    return {name,timezone:zone,active:weekday && minute>=start*60 && minute<end*60,
      heads_up:weekday && minute>=start*60-30 && minute<start*60,
      local_window:`${start}:00–${end}:00`,notice:'Analysis window; not an exchange-open determination. Holidays unverified.'};
  });
}
function report(rawQuote, h1, h4, now) {
  const market={instrument:'ICE DXY cash index',provider:'Barchart OnDemand',symbol:'$DXY',
    quote:quote(rawQuote,now),retrieved_at:new Date(now).toISOString(),
    h1:bars(h1,1,now),h4:bars(h4,4,now)};
  const technical={h1:structure(market.h1),h4:structure(market.h4)};
  const a=technical.h1,b=technical.h4;
  const long=b.direction==='bullish' && a.direction==='bullish' && a.close_above_swing_high;
  const short=b.direction==='bearish' && a.direction==='bearish' && a.close_below_swing_low;
  const potential_setups=(long||short)?[{
    status:'watch_only',direction:long?'long':'short',
    trigger_level:long?a.last_confirmed_high.level:a.last_confirmed_low.level,
    invalidation_level:long?a.last_confirmed_low.level:a.last_confirmed_high.level,
    condition:'Wait for a subsequent completed H1 retest and confirmation; invalidate if H4 alignment is lost.',
    entry:null,tp:null,sl:null,
    missing_checks:['official economic-event risk','executable instrument and broker costs','cost-adjusted reward/risk','retest confirmation'],
    notice:'Index context only; these are not executable prices or a validated trade signal.'
  }]:[];
  return {status:'observations_valid',market_data:market,technical_conditions:technical,potential_setups,
    sessions:sessions(now),valid_until:new Date(Math.min(timestamp(market.quote.event_at)+GRACE,
      ...[1,4].map(h=>(Math.floor((now-GRACE)/(h*HOUR))+1)*h*HOUR+GRACE))).toISOString(),
    monitoring_active:false,notifications_active:false};
}
module.exports={permissions,quote,bars,structure,sessions,report,timestamp};
