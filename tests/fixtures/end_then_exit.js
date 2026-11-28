// The handler answers, then the process exits at once: res.end() ran, but the response never finished sending.
const http = require('http');
const server = http.createServer((req, res) => {
  res.end('bye');
  process.exit(0);
});
server.listen(0, () => http.get(`http://127.0.0.1:${server.address().port}/quit`).on('error', () => {}));
