// Overwrites that reach no read: /early reads `shared` right after its own write, before /blind and /late
// overwrite it; /blind never reads it at all. Neither is a race, and why must not say it is.
const http = require('http');
let shared = null;
const server = http.createServer((req, res) => {
  shared = req.url;
  if (req.url === '/early') {
    const seen = shared;
    setTimeout(function report() { console.log(`early saw ${seen}`); res.end(); }, 40);
  } else if (req.url === '/blind') {
    setTimeout(function report() { console.log('blind done'); res.end(); }, 40);
  } else {
    res.end();
  }
});
server.listen(0, () => {
  const { port } = server.address();
  let n = 0;
  const get = p => http.get({ port, path: p, agent: false }, r => { r.resume(); r.on('end', () => { if (++n === 3) server.close(); }); });
  get('/early');
  setTimeout(() => get('/blind'), 5);
  setTimeout(() => get('/late'), 15);
});
