// Disabled by default. Provider keys remain server-side; no public JSON publication.
const {timingSafeEqual}=require('node:crypto');
const {permissions,report}=require('../lib/dxy.cjs');
module.exports=async function handler(req,res) {
  res.setHeader('Cache-Control','private, no-store');
  res.setHeader('Vary','Authorization');
  const secret=process.env.DASHBOARD_ACCESS_TOKEN;
  if (!secret) return res.status(503).json({status:'not_configured'});
  const expected=Buffer.from(`Bearer ${secret}`),actual=Buffer.from(req.headers.authorization||'');
  if (actual.length!==expected.length || !timingSafeEqual(actual,expected)) return res.status(401).json({status:'unauthorized'});
  if (req.method!=='GET') return res.status(405).json({status:'method_not_allowed'});
  if (process.env.DXY_ENABLED!=='true' || !process.env.BARCHART_API_KEY) return res.status(503).json({status:'disabled_pending_approval'});
  try {
    permissions(process.env.DXY_PERMISSION_RECORD,Date.now());
    async function get(endpoint,params) {
      const response=await fetch(`https://ondemand.websol.barchart.com/${endpoint}.json`,{
        method:'POST',redirect:'error',headers:{'Content-Type':'application/x-www-form-urlencoded'},
        body:new URLSearchParams({apikey:process.env.BARCHART_API_KEY,...params}),signal:AbortSignal.timeout(8000)});
      if (!response.ok) throw Object.assign(Error('provider_unavailable'),{code:response.status===429?'provider_rate_limited':'provider_unavailable'});
      return response.json();
    }
    const now=Date.now(),startDate=new Date(now-40*86400000).toISOString().slice(0,10).replaceAll('-','');
    const history=interval=>get('getHistory',{symbol:'$DXY',type:'minutes',interval:String(interval),startDate,maxRecords:'120',order:'desc'});
    const [q,h1,h4]=await Promise.all([get('getQuote',{symbols:'$DXY'}),history(60),history(240)]);
    return res.status(200).json(report(q,h1,h4,Date.now()));
  } catch(e) {
    const codes=new Set(['entitlement_unverified','invalid_timestamp','provider_rejected','invalid_quote','stale_quote','invalid_candle','insufficient_history','stale_candles','candle_gap','provider_rate_limited']);
    // Never echo upstream text, request body, credentials or old observations on failure.
    return res.status(e.code==='provider_rate_limited'?429:503).json({status:codes.has(e.code)?e.code:'provider_unavailable',market_data:null,technical_conditions:null,potential_setups:[]});
  }
};
