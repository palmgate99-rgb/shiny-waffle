const assert = require('node:assert/strict');
const originalNow = Date.now, originalFetch = global.fetch;
let now;
Date.now = () => now;
process.env.TICKERLAYER_API_KEY = 'test-only';
process.env.DASHBOARD_ACCESS_TOKEN = 'test-only';
function freshHandler() {
  delete require.cache[require.resolve('../api/feed.js')];
  return require('../api/feed.js');
}
const request = {method:'GET',headers:{authorization:'Bearer test-only'},query:{pair:'EURUSD',timeframe:'1h'}};
async function call(handler) {
  const res={headers:{},setHeader(k,v){this.headers[k]=v},status(code){this.code=code;return this},json(body){this.body=body;return this}};
  await handler(request,res);return res;
}
const bar = time => ({o:1,h:1.1,l:.9,c:1,t:Date.parse(time)});
function provider(counters, getBars) {
  return async url => {
    await new Promise(resolve=>setImmediate(resolve));
    if(url.includes('/quote/')) {counters.quote++;return {ok:true,json:async()=>({symbol:'EURUSD',bid:1,ask:1.001,timestamp:now})};}
    counters.bars++;return {ok:true,json:async()=>({symbol:'EURUSD',results:getBars()})};
  };
}
(async()=>{
  for(const start of ['2026-11-13T10:00:01Z','2026-11-13T10:00:11Z']) {
    now=Date.parse(start);const handler=freshHandler(),counts={quote:0,bars:0};
    let bars=[bar('2026-11-13T08:00:00Z')];global.fetch=provider(counts,()=>bars);
    await Promise.all([call(handler),call(handler),call(handler)]);
    assert.deepEqual(counts,{quote:1,bars:1},'simultaneous requests share upstream fetches');
    bars=[bar('2026-11-13T09:00:00Z')];now+=61000;
    const result=await call(handler);
    assert.equal(counts.bars,2,`incomplete response must retry within one minute, including grace window: ${start}`);
    assert.equal(result.body.candles_fresh,true);
    now+=61000;await call(handler);assert.equal(counts.bars,2,'complete candles remain cached within bar');
  }
  now=Date.parse('2026-11-13T10:05:00Z');const handler=freshHandler();let requests=0;
  global.fetch=async()=>{requests++;return {ok:false,status:429,headers:{get:()=> '120'}}};
  assert.equal((await call(handler)).code,429);const first=requests;
  now+=60000;assert.equal((await call(handler)).code,429);assert.equal(requests,first,'cooldown suppresses upstream calls');
  now+=61000;await call(handler);assert.ok(requests>first,'cooldown expires');
  console.log('PASS cache: in-flight sharing, incomplete boundary/grace recovery, complete-bar cache, Retry-After');
})().finally(()=>{Date.now=originalNow;global.fetch=originalFetch}).catch(error=>{console.error(error);process.exitCode=1});
