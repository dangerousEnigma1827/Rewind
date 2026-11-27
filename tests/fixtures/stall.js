// Requests that end every way a request can: ok, failed, cancelled by the client, stuck, and never answered.
//   /ok      responds after a timer; also sets and clears a timer that must not count as pending
//   /fail    responds 500
//   /hang    awaits a promise that never settles
//   /forgot  handler returns without ever calling res.end()
//   /abort   never answered; the client gives up and destroys its socket
// Then the process exits on its own (STALL_HOLD=1: logs an error and stays alive, for kill tests).
const http = require('http');

const server = http.createServer(async (req, res) => {
  if (req.url === '/ok') {
    const t = setTimeout(function neverNeeded() {}, 5000);
    clearTimeout(t);
    setTimeout(function reply() { res.end('ok'); }, 10);
  } else if (req.url === '/fail') {
    res.statusCode = 500; res.end('no');
  } else if (req.url === '/hang') {
    await new Promise(function waitForever() {});
    res.end('unreachable');
  } else if (req.url === '/abort') {
    // never answered; the client destroys the connection
  }
  // '/forgot': falls through without responding
});

function get(port, path, abortAfter) {
  return new Promise(resolve => {
    const req = http.get({ port, path, agent: false }, res => { res.resume(); res.on('end', resolve); });
    req.on('error', resolve);
    if (abortAfter) setTimeout(() => { req.destroy(); resolve(); }, abortAfter);
  });
}

server.listen(0, () => {
  const { port } = server.address();
  for (const p of ['/hang', '/forgot']) http.get({ port, path: p, agent: false }).on('error', () => {});
  Promise.all([get(port, '/ok'), get(port, '/fail'), get(port, '/abort', 30)]).then(() => {
    setTimeout(() => {
      if (process.env.STALL_HOLD) { console.error(new Error('holding')); setInterval(() => {}, 1000); }
      else process.exit(0);
    }, 50);
  });
});
