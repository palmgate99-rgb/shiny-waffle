// Private server-to-server adapter. Keys and access tokens never enter public code.
const {timingSafeEqual} = require('node:crypto');
const PAIRS = new Set(['EURUSD','GBPUSD','USDJPY','USDCAD','USDCHF','AUDUSD','NZDUSD']);
const INTERVALS = {'15m':[15,'minute',900000],'1h':[1,'hour',3600000],'4h':[4,'hour',14400000]};
const cache = new Map(), pending = new Map();
let blockedUntil = 0, providerCalls = 0;
// Per-instance optimization only: not an account-wide quota guarantee.
async function cached(id, expires, load) {
  const hit=cache.get(id);if(hit && hit.expires>Date.now())return hit.value;
  if(pending.has(id))return pending.get(id);
  const work=(async()=>{const value=await load();cache.set(id,{value,expires:typeof expires==='function'?expires(value):expires});return value;})();
  pending.set(id,work);try{return await work;}finally{pending.delete(id);}
}
function normalizeQuote(q,pair,now) {
  if (!q || q.symbol !== pair || ![q.bid,q.ask,q.timestamp].every(Number.isFinite) || q.bid<=0 || q.ask<q.bid || q.timestamp<1e12 || q.timestamp>now+5000) throw Error('schema');
  return {bid:q.bid,ask:q.ask,timestamp:q.timestamp,age_ms:now-q.timestamp,fresh:now-q.timestamp<=120000};
}
function normalizeBars(body,pair,interval,now){
  if(!body || body.symbol!==pair || !Array.isArray(body.results))throw Error('schema');
  const seen=new Set();
  return body.results.filter(b=>{
    if(!b || ![b.o,b.h,b.l,b.c,b.t].every(Number.isFinite) || b.t<1e12 || Math.min(b.o,b.h,b.l,b.c)<=0 || b.h<Math.max(b.o,b.c,b.l) || b.l>Math.min(b.o,b.c,b.h))throw Error('schema');
    if(b.t+interval>now || seen.has(b.t))return false;seen.add(b.t);return true;
  }).sort((a,b)=>a.t-b.t).slice(-300).map(b=>({time:b.t,open:b.o,high:b.h,low:b.l,close:b.c}));
}
async function handler(req,res){
  res.setHeader('Cache-Control','private, no-store');
  const secret=process.env.DASHBOARD_ACCESS_TOKEN,key=process.env.TICKERLAYER_API_KEY;
  if(!secret||!key)return res.status(503).json({status:'not_connected'});
  const expected=Buffer.from(`Bearer ${secret}`),actual=Buffer.from(req.headers.authorization||'');
  if(actual.length!==expected.length||!timingSafeEqual(actual,expected))return res.status(401).json({status:'unauthorized'});
  if(req.method!=='GET')return res.status(405).json({status:'method_not_allowed'});
  const pair=String(req.query.pair||'EURUSD').toUpperCase(),tf=String(req.query.timeframe||'15m');
  if(!PAIRS.has(pair)||!INTERVALS[tf])return res.status(400).json({status:'unsupported_market'});
  const now=Date.now();
  if(now<blockedUntil){res.setHeader('Retry-After',String(Math.ceil((blockedUntil-now)/1000)));return res.status(429).json({status:'provider_cooldown'});}
  async function get(path){
    providerCalls++;
    const r=await fetch('https://api.tickerlayer.com'+path,{headers:{'x-api-key':key},signal:AbortSignal.timeout(8000)});
    if(!r.ok){const e=Error('provider');e.status=r.status;
      if(r.status===429){const raw=r.headers?.get('retry-after'),seconds=Number(raw);const retry=raw&&Number.isFinite(seconds)?seconds*1000:Date.parse(raw)-Date.now();blockedUntil=Date.now()+Math.max(60000,Number.isFinite(retry)?retry:300000);}
      throw e;
    }return r.json();
  }
  try{
    const [n,unit,duration]=INTERVALS[tf];
    const end=new Date(now).toISOString().slice(0,10),start=new Date(now-28*86400000).toISOString().slice(0,10);
    const [q,b]=await Promise.all([
      cached('quote:'+pair,now+60000,async()=>({value:normalizeQuote(await get(`/forex/quote/${pair}`),pair,Date.now()),received:Date.now()})),
      cached('bars:'+pair+tf,v=>{const last=v.value.at(-1),complete=last&&last.time+duration>=Math.floor(Date.now()/duration)*duration;return complete?(Math.floor(Date.now()/duration)+1)*duration+10000:Date.now()+60000;},async()=>({value:normalizeBars(await get(`/forex/agg/${pair}/${n}/${unit}/${start}/${end}?sort=desc&limit=320`),pair,duration,Date.now()),received:Date.now()}))
    ]);
    const checked=Date.now(),quote={...q.value,age_ms:checked-q.value.timestamp,fresh:checked-q.value.timestamp<=120000};
    const last=b.value.at(-1);
    return res.status(200).json({status:quote.fresh?'indicative':'stale',provider:'TickerLayer',pair,timeframe:tf,observed_at:new Date(q.received).toISOString(),candles_observed_at:new Date(b.received).toISOString(),quote,bars:b.value,
      candles_fresh:!!last && last.time+duration>=Math.floor((checked-10000)/duration)*duration,
      cache:{scope:'server instance only',provider_calls_this_instance:providerCalls,next_candle_check_at:new Date((Math.floor(checked/duration)+1)*duration+10000).toISOString()},
      notice:'Indicative OTC data, not Eightcap execution quotes. No qualified trade signals.'});
  }catch(e){if(e.status===429)res.setHeader('Retry-After',String(Math.ceil((blockedUntil-Date.now())/1000)));return res.status(e.status===429?429:502).json({status:e.message==='schema'?'invalid_provider_data':'provider_unavailable'});}
}
module.exports=handler;module.exports.normalizeQuote=normalizeQuote;module.exports.normalizeBars=normalizeBars;
