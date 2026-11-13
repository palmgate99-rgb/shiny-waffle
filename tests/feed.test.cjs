const assert=require('node:assert/strict');let handler=require('../api/feed.js');
const now=Date.now(),pair='EURUSD',q={symbol:pair,bid:1,ask:1.01,timestamp:now};
assert.equal(handler.normalizeQuote(q,pair,now).fresh,true);
assert.equal(handler.normalizeQuote({...q,timestamp:now-180000},pair,now).fresh,false);
for(const bad of [{...q,ask:0},{...q,timestamp:now/1000},{...q,timestamp:now+10000},{...q,bid:null}])assert.throws(()=>handler.normalizeQuote(bad,pair,now));
const b={o:1,h:1.1,l:0.9,c:1,t:Math.floor(now/900000)*900000};
assert.equal(handler.normalizeBars({symbol:pair,results:[b]},pair,900000,now).length,0);
assert.equal(handler.normalizeBars({symbol:pair,results:[{...b,t:b.t-900000}]},pair,900000,now).length,1);
async function call(req){const res={setHeader(){},status(n){this.code=n;return this},json(x){this.body=x;return this}};await handler(req,res);return res}
(async()=>{delete process.env.TICKERLAYER_API_KEY;delete process.env.DASHBOARD_ACCESS_TOKEN;
assert.equal((await call({headers:{}})).code,503);
process.env.TICKERLAYER_API_KEY='test-only';process.env.DASHBOARD_ACCESS_TOKEN='test-only';
assert.equal((await call({headers:{}})).code,401);
const req={headers:{authorization:'Bearer test-only'},method:'GET',query:{pair:'bad'}};assert.equal((await call(req)).code,400);
req.query.pair=pair;global.fetch=async()=>({ok:false,status:429});assert.equal((await call(req)).code,429);
delete require.cache[require.resolve('../api/feed.js')];handler=require('../api/feed.js');
let calls=0;global.fetch=async(url)=>{calls++;return {ok:true,json:async()=>url.includes('/quote/')?q:{symbol:pair,results:[{...b,t:b.t-900000}]}}};
assert.equal((await call(req)).body.status,'indicative');await Promise.all([call(req),call(req)]);assert.equal(calls,2);
req.query.timeframe='1h';await call(req);assert.equal(calls,3); // shared quote across timeframes
console.log('PASS private feed auth, quota, schema, timestamp, closed bars and mock success');})();
