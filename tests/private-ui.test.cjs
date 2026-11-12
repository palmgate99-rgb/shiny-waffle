const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const script=[...fs.readFileSync('smart_money_market_checker.html','utf8').matchAll(/<script>([\s\S]*?)<\/script>/g)][1][1];
const els={},requests=[],pending=[];
const ctx2d=new Proxy({}, {get:()=>()=>{}});
function element(id){return els[id]??=( {value:id==='privatePair'?'EURUSD':id==='privateTf'?'15m':'',textContent:'',width:1000,height:300,handlers:{},addEventListener(e,f){this.handlers[e]=f},getContext(){return ctx2d}})}
const context={document:{getElementById:element},Date,AbortController,setTimeout,clearTimeout,setInterval:()=>{},encodeURIComponent,
fetch:(url,opts)=>{requests.push({url,opts});return new Promise(resolve=>pending.push(resolve));}};
vm.runInNewContext(script,context);
const flush=()=>new Promise(r=>setImmediate(r));
const data=pair=>({status:'indicative',pair,timeframe:'15m',provider:'TickerLayer',observed_at:new Date().toISOString(),quote:{bid:1,ask:1.01,timestamp:Date.now()},bars:[],candles_fresh:false});
(async()=>{
element('privateToken').value='test-only';element('connectPrivate').handlers.click();assert.equal(element('privateToken').value,'');assert.equal(requests[0].opts.headers.Authorization,'Bearer test-only');
element('privatePair').value='GBPUSD';element('privatePair').handlers.change();pending.shift()({ok:true,json:async()=>data('EURUSD')});await flush();assert.equal(requests.length,2);assert.match(requests[1].url,/GBPUSD/);
pending.shift()({ok:true,json:async()=>data('GBPUSD')});await flush();assert.match(element('privateQuote').textContent,/GBPUSD/);
element('disconnectPrivate').handlers.click();assert.equal(element('privateQuote').textContent,'');assert.match(element('privateStatus').textContent,/Disconnected/);
console.log('PASS private UI: memory-only input clearing, bearer request, inflight pair switch and disconnect');})();
