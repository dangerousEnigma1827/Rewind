// the shared in-flight promise REJECTS; both requests catch and log it. Whose error is /b's?
const http = require('http');
let cache = null;
function load() {
  if (!cache) cache = new Promise((_, rej) => setTimeout(function fetchPrice() { rej(new Error('upstream down')); }, 30)); // @CACHE
  return cache;
}
const server = http.createServer(async (req, res) => {
  try { await load(); res.end('ok'); } // @AWAIT
  catch (e) { console.error(e); res.statusCode = 500; res.end('fail ' + req.url); }
});
require('./_serve')(server, [['/a', 0], ['/b', 10]]);
