// Spike-only preload, loaded AFTER recorder/recorder.js: records the context that first calls res.end().
// Writes NDJSON to $REWIND_PROBE_OUT. A prototype for a possible `http.end` recorder event; Rewind doesn't use it.
'use strict';
const OUT = process.env.REWIND_PROBE_OUT;
if (OUT) {
  const ah = require('async_hooks'), fs = require('fs'), http = require('http'), path = require('path');
  const fd = fs.openSync(OUT, 'w');
  const STACK = process.env.PROBE_STACK !== '0';
  const origEnd = http.ServerResponse.prototype.end;
  const seen = new WeakSet();
  http.ServerResponse.prototype.end = function end(...args) {
    if (!seen.has(this)) {
      seen.add(this);
      let stack = null;
      if (STACK) {
        const prev = Error.prepareStackTrace, lim = Error.stackTraceLimit;
        Error.prepareStackTrace = (_, cs) => cs; Error.stackTraceLimit = 20;
        const h = {}; Error.captureStackTrace(h, end);
        const cs = h.stack; Error.prepareStackTrace = prev; Error.stackTraceLimit = lim;
        stack = cs.filter(c => c.getFileName() && !c.getFileName().startsWith('node:') && c.getFileName() !== __filename)
          .slice(0, 4).map(c => `${c.getFunctionName() || '<anonymous>'}@${path.basename(c.getFileName())}:${c.getLineNumber()}`);
      }
      fs.writeSync(fd, JSON.stringify({ kind: 'probe.end', url: this.req && this.req.url,
        eid: ah.executionAsyncId(), tid: ah.triggerAsyncId(), stack }) + '\n');
    }
    return origEnd.apply(this, args);
  };
}
