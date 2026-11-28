// A shared in-flight promise rejects. /a handles it; /b doesn't, so /b's handler dies with an unhandled rejection.
const http = require('http');
let cache = null;
function load() {
  if (!cache) cache = new Promise((_, rej) => setTimeout(function fetchPrice() { rej(new Error('upstream down')); }, 30));
  return cache;
}
const server = http.createServer(async (req, res) => {
  if (req.url === '/a') {
    try { await load(); } catch (e) { res.statusCode = 503; }
    return res.end('a');
  }
  await load(); // /b: no catch
  res.end('b');
});
require('./_serve')(server, [['/a', 0], ['/b', 10]]);
