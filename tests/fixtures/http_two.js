const http = require('http'), fsp = require('fs/promises');
const { setTimeout: sleep } = require('timers/promises');
const server = http.createServer(async (req, res) => {
  const id = req.url.slice(1);
  await fsp.readFile(__filename);
  await sleep(id === '1' ? 15 : 2);
  console.log('done ' + id);
  if (id === '2') console.error(new Error('logged failure 2'));
  res.statusCode = id === '2' ? 500 : 200;
  res.end(id);
});
server.listen(0, () => {
  const port = server.address().port; let left = 2;
  for (const id of ['1', '2']) http.get(`http://127.0.0.1:${port}/${id}`, r => { r.resume(); r.on('end', () => { if (--left === 0) server.close(); }); });
});
