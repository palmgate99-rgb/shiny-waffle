const assert=require('node:assert/strict'),observe=require('../assets/technical-context.js');
const flat=Array.from({length:30},()=>({open:10,close:10,high:11,low:9}));
assert.equal(observe([]).ready,false);assert.equal(observe(flat).rsi,50);
const rising=flat.map((b,i)=>({open:i+1,close:i+1,low:i+.5,high:i+1.5}));
assert.equal(observe(rising).rsi,100);assert.match(observe(rising).priceAction,/above/);
const bullish=[...flat,{open:10,close:10,low:9,high:11},{open:10,close:10,low:8,high:10.5},{open:10,close:11,low:9,high:12}];
assert.match(observe(bullish).crt,/Bullish/);
const both=[...bullish];both[both.length-2]={open:10,close:10,low:8,high:12};assert.match(observe(both).crt,/No confirmed/);
assert.match(observe(bullish).smt,/Not checked/);console.log('PASS RSI, CRT, price-action and SMT fail-closed definitions');
