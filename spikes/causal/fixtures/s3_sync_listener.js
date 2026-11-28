// S3f: /b registers a plain listener; /a's code emits synchronously. No async resource is involved.
const http = require('http'), { EventEmitter } = require('events');
const bus = new EventEmitter();
const server = http.createServer((req, res) => {
  if (req.url === '/b') { bus.on('tick', function bListener() { console.log('b listener ran'); }); return res.end('b'); }
  setTimeout(function emitter() { bus.emit('tick'); res.end('a'); }, 20);
});
require('./_serve')(server, [['/b', 0], ['/a', 5]]);
