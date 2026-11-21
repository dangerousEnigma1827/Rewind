// M0 spike recorder: minimal, measures assumptions. Not production code.
'use strict';
const ah = require('async_hooks');
const fs = require('fs');
const OUT = process.env.REWIND_OUT;
const STACKS = process.env.REWIND_STACKS !== '0';
const PROMISE_STACKS = process.env.REWIND_PROMISE_STACKS === '1';
const fd = fs.openSync(OUT, 'w');
const t0 = process.hrtime.bigint();
let seq = 0, buf = [], inHook = false;
const active = [];               // aids whose callback is currently running
const promiseAid = new WeakMap(); // promise -> aid (E3)

function stack() {
  const lim = Error.stackTraceLimit; Error.stackTraceLimit = 12;
  const s = new Error().stack.split('\n').slice(1).map(l => l.trim().replace(/^at /, ''))
    .filter(l => !l.includes(__filename) && !l.startsWith('node:') && !l.includes('(node:'));
  Error.stackTraceLimit = lim; return s.slice(0, 8);
}
function emit(kind, f) {
  buf.push(JSON.stringify({ seq: seq++, t: Number(process.hrtime.bigint() - t0) / 1000, kind,
    eid: ah.executionAsyncId(), top: active[active.length - 1] ?? null, ...f }));
  if (buf.length >= 256) flush();
}
function flush() { if (buf.length) { fs.writeSync(fd, buf.join('\n') + '\n'); buf = []; } }

ah.createHook({
  init(aid, type, tid, res) {
    if (inHook) return; inHook = true;
    if (type === 'PROMISE') promiseAid.set(res, aid);
    const cb = res && (res._onTimeout || res._onImmediate);
    emit('async.init', { aid, tid, type, cb: cb ? (cb.name || '(anonymous)') : undefined, stack: STACKS && (type !== 'PROMISE' || PROMISE_STACKS) ? stack() : null });
    inHook = false;
  },
  before(aid) { active.push(aid); if (!inHook) emit('async.before', { aid }); },
  after(aid) { if (!inHook) emit('async.after', { aid }); active.pop(); },
  promiseResolve(aid) { if (!inHook) emit('async.resolve', { aid }); },
}).enable();

const origLog = console.log;
console.log = function (...a) { emit('log', { name: a.map(String).join(' ') }); return origLog.apply(this, a); };
globalThis.__rewindMark = (name) => emit('mark', { name });

process.on('uncaughtExceptionMonitor', (err, origin) => {
  emit('error.uncaught', { name: String(err && err.message), origin, stack: String(err && err.stack).split('\n').slice(1, 6).map(s => s.trim()) });
});
if (process.env.REWIND_REJECTION_HANDLER === '1') {
  process.on('unhandledRejection', (reason, p) => {
    emit('error.rejection', { name: String(reason && reason.message), aid: promiseAid.get(p) ?? null });
    throw reason; // preserve default crash behaviour
  });
}
process.on('exit', (code) => { emit('run.end', { data: { code } }); flush(); fs.closeSync(fd); });
emit('run.start', { data: { argv: process.argv.slice(1) } });
