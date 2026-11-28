// Responses are queued and sent by a module-level timer that belongs to no request.
const http = require('http');
const queue = [];
const flusher = setInterval(function flush() { while (queue.length) queue.shift().end('queued'); }, 15);
const server = http.createServer((req, res) => { queue.push(res); });
server.on('close', () => clearInterval(flusher));
require('./_serve')(server, [['/q', 0]]);
