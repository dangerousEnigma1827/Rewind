// Test client: starts `server`, sends `paths` (each after its delay in ms), closes when all responses are in.
const http = require('http');
module.exports = function serve(server, paths) {
  server.listen(0, () => {
    const port = server.address().port; let left = paths.length;
    for (const [path, delay] of paths)
      setTimeout(() => http.get(`http://127.0.0.1:${port}${path}`, r => {
        r.resume(); r.on('end', () => { if (--left === 0) server.close(); });
      }), delay);
  });
};
