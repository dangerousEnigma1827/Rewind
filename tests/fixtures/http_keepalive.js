// three requests on ONE keep-alive socket; each reads its body on 'end', then schedules work
const http = require('http');
const server = http.createServer((req, res) => {
  let body = '';
  req.on('data', c => (body += c));
  req.on('end', () => setTimeout(function work() { console.log('done ' + body); res.end(body); }, 2));
});
server.listen(0, async () => {
  const agent = new http.Agent({ keepAlive: true, maxSockets: 1 });
  for (const id of ['a', 'b', 'c']) {
    await new Promise(ok => {
      const r = http.request({ port: server.address().port, method: 'POST', agent }, res => { res.resume(); res.on('end', ok); });
      r.end(id);
    });
  }
  agent.destroy(); server.close();
});
