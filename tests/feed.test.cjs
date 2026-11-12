const assert = require('node:assert/strict');
const handler=require('../api/feed.js');
async function call(req){const res={setHeader(){},status(n){this.code=n;return this},json(x){this.body=x;return this}};await handler(req,res);return res}
(async()=>{delete process.env.TICKERLAYER_API_KEY;delete process.env.DASHBOARD_ACCESS_TOKEN;
assert.equal((await call({headers:{}})).code,503);
process.env.TICKERLAYER_API_KEY='test-only';process.env.DASHBOARD_ACCESS_TOKEN='test-only';
assert.equal((await call({headers:{}})).code,401);
const req={headers:{authorization:'Bearer test-only'},method:'GET',query:{pair:'notallowed'}};
assert.equal((await call(req)).code,400);
req.query.pair='EURUSD';global.fetch=async()=>({ok:false,status:429});assert.equal((await call(req)).code,429);
global.fetch=async()=>({ok:true,json:async()=>({timestamp:'example'})});assert.equal((await call(req)).body.status,'indicative_quote_only');
console.log('PASS private adapter: missing config, unauthorized, allowlist, quota, success (mocked)');})();
