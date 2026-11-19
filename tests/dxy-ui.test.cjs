const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
test('DXY panel sends only dashboard token, clears failures, expires, and ignores superseded responses',async()=>{
  const elements={},pending=[],requests=[],timers=new Map();let timer=0;
  const element=id=>elements[id]??=( {value:'',textContent:''});
  const c={document:{getElementById:element},Date,AbortController,JSON,
    setTimeout:(f,ms)=>{timers.set(++timer,{f,ms});return timer;},clearTimeout:id=>timers.delete(id),
    fetch:(url,opts)=>{requests.push({url,opts});return new Promise(r=>pending.push(r));}};
  vm.runInNewContext(fs.readFileSync('dxy.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1],c);
  const data=()=>({status:'observations_valid',valid_until:new Date(Date.now()+60000).toISOString(),market_data:{symbol:'$DXY'},technical_conditions:{h1:'undetermined'},potential_setups:[],sessions:[]});
  element('token').value='test-access';const first=element('load').onclick();assert.equal(element('token').value,'');assert.equal(requests[0].url,'/api/dxy');assert.equal(requests[0].opts.headers.Authorization,'Bearer test-access');
  pending.shift()({ok:true,json:async()=>data()});await first;assert.match(element('market').textContent,/DXY/);
  [...timers.values()].find(x=>x.ms<61000 && x.ms>59000).f();assert.equal(element('market').textContent,'Unavailable');assert.match(element('status').textContent,/expired/);
  element('token').value='test-access';const second=element('load').onclick();pending.shift()({ok:false,json:async()=>({status:'stale_quote'})});await second;assert.equal(element('technical').textContent,'Unavailable');assert.match(element('status').textContent,/stale_quote/);
  element('token').value='test-access';const third=element('load').onclick();element('clear').onclick();pending.shift()({ok:true,json:async()=>data()});await third;assert.equal(element('market').textContent,'Unavailable');
});
