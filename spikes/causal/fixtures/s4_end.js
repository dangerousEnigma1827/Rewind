// S4: where res.end() is called from. /park is parked and ended later by /release's handler.
const http = require('http'), fs = require('fs');
let parked = null;
const server = http.createServer(async (req, res) => {
  switch (req.url) {
    case '/direct': return res.end('direct'); // @DIRECT
    case '/await': await new Promise(r => setTimeout(r, 2)); return res.end('await'); // @AWAITEND
    case '/timer': return setTimeout(function later() { res.end('timer'); }, 3); // @TIMEREND
    case '/pipe': return fs.createReadStream(__filename).pipe(res); // @PIPE
    case '/park': parked = res; return;
    case '/release': parked.end('released'); return res.end('release'); // @RELEASE
  }
});
require('./_serve')(server, [['/direct', 0], ['/await', 0], ['/timer', 0], ['/pipe', 0], ['/park', 0], ['/release', 30]]);
