// Private server-to-server adapter. Keys and access tokens never enter public code.
const {timingSafeEqual} = require('node:crypto');
const PAIRS = new Set(['EURUSD','GBPUSD','USDJPY','USDCAD','USDCHF','AUDUSD','NZDUSD']);
const INTERVALS = {'15m':[15,'minute',900000],'1h':[1,'hour',3600000],'4h':[4,'hour',14400000]};
const cache = new Map();
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
  }).sort((a,b)=>a.t-b.t).slice(-80).map(b=>({time:b.t,open:b.o,high:b.h,low:b.l,close:b.c}));
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
  const now=Date.now(),cacheKey=pair+tf;
  async function get(path){const r=await fetch('https://api.tickerlayer.com'+path,{headers:{'x-api-key':key},signal:AbortSignal.timeout(8000)});if(!r.ok){const e=Error('provider');e.status=r.status;throw e;}return r.json();}
  try{
    let data=cache.get(cacheKey);
    if(!data||now-data.observed_ms>=60000){
      const [n,unit,duration]=INTERVALS[tf];
      const end=new Date(now).toISOString().slice(0,10),start=new Date(now-7*86400000).toISOString().slice(0,10);
      const [rawQuote,rawBars]=await Promise.all([get(`/forex/quote/${pair}`),get(`/forex/agg/${pair}/${n}/${unit}/${start}/${end}?sort=desc&limit=100`)]);
      const received=Date.now();
      const quote=normalizeQuote(rawQuote,pair,received),bars=normalizeBars(rawBars,pair,duration,received);
      data={observed_ms:now,quote,bars};cache.set(cacheKey,data);
    }
    const quote={...data.quote,age_ms:now-data.quote.timestamp,fresh:now-data.quote.timestamp<=120000};
    const duration=INTERVALS[tf][2],last=data.bars.at(-1);
    return res.status(200).json({status:quote.fresh?'indicative':'stale',provider:'TickerLayer',pair,timeframe:tf,observed_at:new Date(data.observed_ms).toISOString(),quote,bars:data.bars,
      candles_fresh:!!last && now-(last.time+duration)<=duration+120000,
      notice:'Indicative OTC data, not Eightcap execution quotes. No qualified trade signals.'});
  }catch(e){return res.status(e.status===429?429:502).json({status:e.message==='schema'?'invalid_provider_data':'provider_unavailable'});}
}
module.exports=handler;module.exports.normalizeQuote=normalizeQuote;module.exports.normalizeBars=normalizeBars;
