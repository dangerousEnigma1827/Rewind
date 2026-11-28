// S3d: /b awaits events.once(emitter, 'ready'); /a emits 'ready' from its own callback.
const http = require('http'), { once, EventEmitter } = require('events');
const bus = new EventEmitter();
const server = http.createServer(async (req, res) => {
  if (req.url === '/b') { await once(bus, 'ready'); console.log('b saw ready'); return res.end('b'); } // @ONCE
  setTimeout(function announce() { bus.emit('ready'); res.end('a'); }, 20);
});
require('./_serve')(server, [['/a', 0], ['/b', 5]]);
