// Synthetic fixtures exercise rejection logic only; never published as market data.
const {test}=require('node:test'),assert=require('node:assert/strict');
const {permissions,quote,bars,structure,sessions,report}=require('../lib/dxy.cjs');
const handler=require('../api/dxy');
const H=3600000,now=Date.parse('2026-11-19T16:05:00Z'),iso=t=>new Date(t).toISOString();
const body=results=>({status:{code:200},results});
const q=()=>body([{symbol:'$DXY',mode:'R',lastPrice:100,tradeTimestamp:iso(now-1000)}]);
function history(h){return body(Array.from({length:25},(_,i)=>({symbol:'$DXY',timestamp:iso(Math.floor(now/(h*H))*h*H-(24-i)*h*H),open:100,high:102,low:98,close:101})));}
const permission=()=>({provider:'Barchart OnDemand',symbol:'$DXY',instrument:'ICE DXY cash index',use:'private_display_and_analysis',realtime:true,history:true,timestamp_semantics:'bar_start',utc_aligned_full_bars:true,evidence_ref:'test-only',verified_at:iso(now-1000),expires_at:iso(now+H)});
test('permissions require recent documented entitlement and matching instrument',()=>{
  assert.equal(permissions(JSON.stringify(permission()),now).symbol,'$DXY');
  for(const change of [{symbol:'DXZ26'},{realtime:false},{evidence_ref:''},{expires_at:iso(now)},{verified_at:iso(now-31*86400000)},{timestamp_semantics:'end'}])assert.throws(()=>permissions(JSON.stringify({...permission(),...change}),now));
  assert.throws(()=>permissions(undefined,now));
});
test('quote uses event time, rejects delayed, future, stale, wrong-symbol and missing time',()=>{
  assert.equal(quote(q(),now).age_ms,1000);
  for(const change of [{mode:'I'},{mode:'D'},{symbol:'USDX'},{tradeTimestamp:iso(now+1)},{tradeTimestamp:iso(now-120001)},{tradeTimestamp:'2026-11-19T16:00:00'},{lastPrice:NaN}]){
    const input=q();Object.assign(input.results[0],change);assert.throws(()=>quote(input,now));
  }
});
test('native closed bars reject duplicates, gaps, misalignment, invalid OHLC and stale latest',()=>{
  const b=bars(history(1),1,now);assert.equal(b.length,24);assert.equal(b.at(-1).end_ms,Date.parse('2026-11-19T16:00:00Z'));
  assert.equal(bars(history(4),4,now).at(-1).end_ms,Date.parse('2026-11-19T16:00:00Z'));
  const change=[x=>x.results.push(x.results[0]),x=>x.results.splice(5,1),x=>x.results[0].high=99,x=>x.results[0].timestamp=iso(now-111),x=>x.results=x.results.slice(0,-2)];
  for(const f of change){const x=history(1);f(x);assert.throws(()=>bars(x,1,now));}
  assert.throws(()=>bars(history(1),1,Date.parse('2026-11-19T18:05:00Z')),/stale_candles/);
});
test('bar close grace excludes newly closed bar and advances expected close at boundary',()=>{
  const boundary=Date.parse('2026-11-19T16:01:59Z');assert.equal(bars(history(1),1,boundary).at(-1).end_ms,Date.parse('2026-11-19T15:00:00Z'));
});
test('structure needs confirmed swings and no lookahead',()=>{
  const flat=bars(history(1),1,now);assert.equal(structure(flat).direction,'undetermined');
  const levels=[2,3,5,3,2,3,4,6,4,3,4,5,7,5,4,5];
  const candles=levels.map((x,i)=>({start_ms:i*H,end_ms:(i+1)*H,open:x,high:x+1,low:x-1,close:x}));
  const s=structure(candles);assert.equal(s.direction,'bullish');assert.equal(s.last_confirmed_high.confirmed_at,15*H);
  assert.equal(structure(candles.slice(0,14)).last_confirmed_high.level,7);
});
test('session planning honors London/New York DST difference and heads-up window',()=>{
  assert.equal(sessions(Date.parse('2026-03-16T11:45:00Z')).find(s=>s.name==='New York').heads_up,true);
  assert.equal(sessions(Date.parse('2026-11-19T12:45:00Z')).find(s=>s.name==='New York').heads_up,true);
  assert.equal(sessions(Date.parse('2026-11-21T14:00:00Z')).some(s=>s.active),false);
});
test('report separates evidence and conditions; expires by event freshness',()=>{
  const d=report(q(),history(1),history(4),now);
  assert.equal(d.monitoring_active,false);assert.equal(d.notifications_active,false);assert.deepEqual(d.potential_setups,[]);
  assert.equal(Date.parse(d.valid_until),now-1000+120000);
});
function response(){return {headers:{},setHeader(k,v){this.headers[k]=v;},status(n){this.statusCode=n;return this;},json(b){this.body=b;return this;}};}
test('API fails closed before network; credentials never echoed',async()=>{
  const original={...process.env},fetchOriginal=global.fetch;let calls=0;
  global.fetch=async()=>{calls++;throw Error('secret-provider-error');};
  try{
    process.env.DASHBOARD_ACCESS_TOKEN='test-dashboard-secret';delete process.env.DXY_ENABLED;
    let r=response();await handler({method:'GET',headers:{authorization:'Bearer wrong'}},r);assert.equal(r.statusCode,401);
    r=response();await handler({method:'GET',headers:{authorization:'Bearer test-dashboard-secret'}},r);assert.equal(r.statusCode,503);assert.equal(calls,0);
    process.env.DXY_ENABLED='true';process.env.BARCHART_API_KEY='test-provider-secret';process.env.DXY_PERMISSION_RECORD='{}';
    r=response();await handler({method:'GET',headers:{authorization:'Bearer test-dashboard-secret'}},r);assert.equal(r.body.status,'entitlement_unverified');assert.equal(calls,0);assert.equal(r.headers['Cache-Control'],'private, no-store');
  }finally{process.env=original;global.fetch=fetchOriginal;}
});
test('API uses fixed POST routes and withholds all data when a provider response fails',async()=>{
  const original={...process.env},fetchOriginal=global.fetch,clock=Date.now,requests=[];
  let delayed=false;
  try{
    Date.now=()=>now;
    Object.assign(process.env,{DASHBOARD_ACCESS_TOKEN:'test-dashboard-secret',DXY_ENABLED:'true',BARCHART_API_KEY:'test-provider-secret',DXY_PERMISSION_RECORD:JSON.stringify(permission())});
    global.fetch=async(url,opts)=>{
      requests.push({url,opts});
      const input=new URLSearchParams(opts.body);
      let data;
      if(url.endsWith('/getQuote.json')){data=q();if(delayed)data.results[0].mode='I';}
      else data=history(Number(input.get('interval'))/60);
      return {ok:true,json:async()=>data};
    };
    const req={method:'GET',headers:{authorization:'Bearer test-dashboard-secret'}};
    let r=response();await handler(req,r);assert.equal(r.statusCode,200);assert.equal(requests.length,3);
    for(const {url,opts} of requests){assert.equal(opts.method,'POST');assert.equal(opts.redirect,'error');assert.equal(new URL(url).hostname,'ondemand.websol.barchart.com');assert.ok(!url.includes('secret'));}
    assert.ok(!JSON.stringify(r.body).includes('secret'));
    delayed=true;r=response();await handler(req,r);assert.equal(r.statusCode,503);assert.equal(r.body.market_data,null);assert.deepEqual(r.body.potential_setups,[]);
  }finally{Date.now=clock;process.env=original;global.fetch=fetchOriginal;}
});
test('aligned structure breakout produces only a conditional watch with no executable levels',()=>{
  function trending(h){
    const levels=[2,3,5,3,2,3,4,6,4,3,4,5,7,5,4,5,9];
    const end=Math.floor(now/(h*H))*h*H;
    return body(levels.map((x,i)=>({symbol:'$DXY',timestamp:iso(end-(levels.length-i)*h*H),open:x,high:x+1,low:x-1,close:x})));
  }
  const d=report(q(),trending(1),trending(4),now);
  assert.equal(d.potential_setups.length,1);const s=d.potential_setups[0];
  assert.equal(s.direction,'long');assert.equal(s.status,'watch_only');assert.equal(s.entry,null);assert.equal(s.tp,null);assert.equal(s.sl,null);
});
