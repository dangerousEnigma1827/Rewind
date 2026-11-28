// memoised IN-FLIGHT promise shared by concurrent requests (cache fill / single-flight).
const http = require('http');
let cache = null;
function load() {
  if (!cache) cache = new Promise(r => setTimeout(function fetchPrice() { r({ price: 10 }); }, 30)); // @CACHE
  return cache;
}
const server = http.createServer(async (req, res) => {
  const v = await load(); // @AWAIT
  console.log(`handler ${req.url} ${v.price}`);
  res.end('ok');
});
require('./_serve')(server, [['/a', 0], ['/b', 10]]);
