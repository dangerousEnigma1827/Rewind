// One request awaits in a long loop: each continuation is created by the previous one, so the creation chain of
// the last one is thousands of links deep.
const http = require('http');
const N = +process.env.AWAITS || 3000;
const server = http.createServer(async (req, res) => {
  for (let i = 0; i < N; i++) await null;
  console.log(`looped ${N}`);
  res.end('ok');
});
require('./_serve')(server, [['/loop', 0]]);
