// S3b: the shared promise has ALREADY settled when request /b awaits it (plain cache hit).
const http = require('http');
let cache = null;
function load() {
  if (!cache) cache = new Promise(r => setTimeout(function fetchPrice() { r({ price: 10 }); }, 5)); // @CACHE
  return cache;
}
const server = http.createServer(async (req, res) => {
  const v = await load(); // @AWAIT
  console.log(`handler ${req.url} ${v.price}`);
  res.end('ok');
});
require('./_serve')(server, [['/a', 0], ['/b', 60]]);
