// demo-sized-plus workload: N http requests, each: fs read, await timer, a few promises, json
const http = require('http'), fsp = require('fs/promises');
const N = +process.env.N || 300;
const srv = http.createServer(async (req, res) => {
  const txt = await fsp.readFile(__filename, 'utf8');
  await new Promise(r => setTimeout(r, 1));
  const parts = await Promise.all([1, 2, 3].map(async i => txt.length * i));
  res.end(JSON.stringify(parts));
});
srv.listen(0, async () => {
  const port = srv.address().port, t = Date.now();
  for (let b = 0; b < N / 10; b++)
    await Promise.all(Array.from({ length: 10 }, () => fetch(`http://127.0.0.1:${port}/`).then(r => r.text())));
  srv.close(); process.stderr.write(`REQ_MS ${Date.now() - t}\n`);
});
