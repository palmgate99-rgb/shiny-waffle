// Deterministic closed-candle observations, NOT a validated trade strategy.
(function(root){
  function technicalContext(bars){
    if(!Array.isArray(bars)||bars.length<21)return {ready:false,reason:'At least 21 closed bars required',rsi:null,crt:'Unavailable',priceAction:'Unavailable',smt:'Not checked: synchronized comparison market required'};
    const closes=bars.map(b=>b.close);let gain=0,loss=0;
    for(let i=1;i<=14;i++){const delta=closes[i]-closes[i-1];gain+=Math.max(0,delta)/14;loss+=Math.max(0,-delta)/14;}
    for(let i=15;i<closes.length;i++){const delta=closes[i]-closes[i-1];gain=(gain*13+Math.max(0,delta))/14;loss=(loss*13+Math.max(0,-delta))/14;}
    const rsi=gain===0&&loss===0?50:loss===0?100:100-100/(1+gain/loss);
    const [range,sweep,confirmation]=bars.slice(-3),prior=bars.slice(-21,-1),high=Math.max(...prior.map(b=>b.high)),low=Math.min(...prior.map(b=>b.low));
    // CRT definition: range candle, one-sided sweep closing back inside range,
    // then a third close beyond the sweep candle in the opposite direction.
    const inside=sweep.close>range.low&&sweep.close<range.high;
    const bullish=inside&&sweep.low<range.low&&sweep.high<=range.high&&confirmation.close>sweep.high;
    const bearish=inside&&sweep.high>range.high&&sweep.low>=range.low&&confirmation.close<sweep.low;
    return {ready:true,rsi,crt:bullish?'Bullish three-candle reclaim':bearish?'Bearish three-candle reclaim':'No confirmed three-candle reclaim',priceAction:confirmation.close>high?'Close above prior 20-bar high':confirmation.close<low?'Close below prior 20-bar low':'Inside prior 20-bar range',smt:'Not checked: synchronized comparison market required'};
  }
  if(typeof module!=='undefined')module.exports=technicalContext;else root.technicalContext=technicalContext;
})(typeof window!=='undefined'?window:globalThis);
