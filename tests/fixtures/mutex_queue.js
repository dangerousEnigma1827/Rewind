// a mutex with a resolver queue. /b waits; /a's own timer callback calls /b's resolve() on unlock.
const http = require('http');
let locked = false; const waiters = [];
function lock() {
  if (!locked) { locked = true; return Promise.resolve(); }
  return new Promise(r => waiters.push(r)); // @WAIT
}
function unlock() { const next = waiters.shift(); if (next) next(); else locked = false; }
const server = http.createServer(async (req, res) => {
  await lock(); // @AWAIT
  console.log(`in critical section ${req.url}`);
  setTimeout(function work() { unlock(); res.end('ok'); }, 20); // @WORK
});
require('./_serve')(server, [['/a', 0], ['/b', 5]]);
