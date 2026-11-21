// Rewind execution recorder. Preload with: node --require <path>/recorder.js app.js
// Writes one JSON event per line to $REWIND_OUT. Inert when REWIND_OUT is unset.
// Design constraints validated in spikes/RESULTS.md (M0):
//   - never create async work from inside hooks (sync writes only, re-entrancy guard)
//   - flush every FLUSH_EVERY events, immediately on error events, and on exit
//   - error context comes from executionAsyncId() inside uncaughtExceptionMonitor
'use strict';
const OUT = process.env.REWIND_OUT;
if (OUT && !globalThis.__rewind) {
  const ah = require('async_hooks');
  const fs = require('fs');
  const path = require('path');
  const util = require('util');

  const FLUSH_EVERY = 256;
  const PROMISE_STACKS = process.env.REWIND_PROMISE_STACKS !== '0';
  const WATCH = (process.env.REWIND_WATCH || '').split(',').map(s => s.trim()).filter(Boolean);
  const MUT_CAP = +process.env.REWIND_MUT_CAP || 10000; // per watched name
  const HERE = __dirname;
  const CWD = process.cwd();

  const fd = fs.openSync(OUT, 'w');
  const t0 = process.hrtime.bigint();
  let seq = 0, buf = [], inHook = false, closed = false;

  // ---- stacks -------------------------------------------------------------
  const relFile = f => (f && path.isAbsolute(f) && f.startsWith(CWD) ? path.relative(CWD, f) : f).split(path.sep).join('/');
  const keepFile = f => f && !f.startsWith('node:') && !f.startsWith(HERE);
  // Structured frames straight from V8 CallSites (no string parsing on the hot path).
  function callsites() {
    const prev = Error.prepareStackTrace, lim = Error.stackTraceLimit;
    Error.prepareStackTrace = (_, cs) => cs;
    Error.stackTraceLimit = 20;
    const holder = {};
    Error.captureStackTrace(holder, callsites);
    const cs = holder.stack;
    Error.prepareStackTrace = prev; Error.stackTraceLimit = lim;
    const out = [];
    for (const c of cs) {
      const file = c.getFileName();
      if (!keepFile(file)) continue;
      const fn = c.getFunctionName(), ty = c.getTypeName();
      out.push({ fn: fn ? (ty && ty !== 'Object' && !fn.startsWith(ty + '.') ? `${ty}.${fn}` : fn) : '<anonymous>',
        file: relFile(file), line: c.getLineNumber(), col: c.getColumnNumber() });
      if (out.length === 8) break;
    }
    return out;
  }
  // Thrown errors already carry a formatted .stack string; parse V8's format.
  const FRAME = /^\s*at (?:(.*?) \()?(.*?):(\d+):(\d+)\)?$/;
  function parseStack(s) {
    const out = [];
    for (const line of String(s || '').split('\n')) {
      const m = FRAME.exec(line);
      if (!m || !keepFile(m[2])) continue;
      out.push({ fn: (m[1] || '<anonymous>').replace(/ \[as [^\]]+\]$/, ''), file: relFile(m[2]), line: +m[3], col: +m[4] });
    }
    return out;
  }
  const errInfo = e => e instanceof Error || (e && typeof e === 'object' && 'stack' in e)
    ? { error: e.constructor && e.constructor.name, message: String(e.message), raw: String(e.stack) }
    : { error: typeof e, message: safeFormat([e]), raw: null };
  function safeFormat(args) { try { return util.format(...args); } catch { return '[unformattable]'; } }

  // ---- output ---------------------------------------------------------------
  function emit(kind, f, urgent) {
    if (closed) return;
    const ev = { seq: seq++, t: Number(process.hrtime.bigint() - t0) / 1000, kind, eid: ah.executionAsyncId(), ...f };
    let line;
    try { line = JSON.stringify(ev); } catch { line = JSON.stringify({ seq: ev.seq, t: ev.t, kind, eid: ev.eid, name: '[unserializable]' }); }
    buf.push(line);
    if (urgent || buf.length >= FLUSH_EVERY) flush();
  }
  function flush() {
    if (!buf.length || closed) return;
    const s = buf.join('\n') + '\n'; buf = [];
    try { fs.writeSync(fd, s); } catch { /* disk full / fd gone: nothing safe left to do */ }
  }
  // Every recorder entry point runs under this guard so its own work is never recorded.
  function guarded(fn) { if (inHook) return; inHook = true; try { fn(); } finally { inHook = false; } }

  // ---- async lifecycle ------------------------------------------------------
  ah.createHook({
    init(aid, type, tid, res) {
      guarded(() => {
        const cb = res && (res._onTimeout || res._onImmediate);
        emit('async.init', { aid, tid, type, name: cb ? (cb.name || '<anonymous>') : null,
          stack: type !== 'PROMISE' || PROMISE_STACKS ? callsites() : null });
      });
    },
    before(aid) { guarded(() => emit('async.before', { aid })); },
    after(aid) { guarded(() => emit('async.after', { aid })); },
    promiseResolve(aid) { guarded(() => emit('async.resolve', { aid })); },
  }).enable();

  // ---- console ---------------------------------------------------------------
  for (const level of ['log', 'info', 'warn', 'error', 'debug']) {
    const orig = console[level];
    console[level] = function (...args) {
      guarded(() => {
        emit('log', { name: safeFormat(args), data: { level } });
        for (const a of args) if (a instanceof Error)
          emit('error.logged', { name: a.message, data: errInfo(a), stack: parseStack(a.stack) }, true);
      });
      return orig.apply(this, args);
    };
  }

  // ---- http server -----------------------------------------------------------
  let reqSeq = 0;
  const http = require('http');
  const origEmit = http.Server.prototype.emit;
  // Node's HTTPINCOMINGMESSAGE resource is per *connection*: with keep-alive every request on a socket shares
  // it. So each request gets its own AsyncResource anchor, and the handler plus all req/res event callbacks
  // (data, end, finish, ...) run in its scope. Everything a request schedules then descends from its anchor.
  http.Server.prototype.emit = function (ev, req, res) {
    if (ev !== 'request' || !req || !res || inHook) return origEmit.apply(this, arguments);
    const id = ++reqSeq, start = process.hrtime.bigint();
    const anchor = new ah.AsyncResource('REWIND_REQUEST');
    for (const em of [req, res]) {
      const orig = em.emit;
      em.emit = function () { return anchor.runInAsyncScope(orig, this, ...arguments); };
    }
    res.once('finish', () => guarded(() => emit('http.out', { name: `${res.statusCode} ${req.method} ${req.url}`,
      data: { req: id, status: res.statusCode, ms: Number(process.hrtime.bigint() - start) / 1e6 } }, res.statusCode >= 500)));
    const args = arguments;
    return anchor.runInAsyncScope(() => {
      guarded(() => emit('http.in', { aid: anchor.asyncId(), name: `${req.method} ${req.url}`, data: { req: id, method: req.method, url: req.url } }));
      return origEmit.apply(this, args);
    });
  };

  // ---- errors ------------------------------------------------------------------
  // Monitor only: observes without changing crash semantics or exit codes (E2/E3).
  process.on('uncaughtExceptionMonitor', (err, origin) => {
    guarded(() => emit('error.uncaught', { name: errInfo(err).message, data: { origin, ...errInfo(err) }, stack: parseStack(err && err.stack) }, true));
  });

  // ---- mutation tracking (opt-in; AST deps loaded only here) -------------------
  const mutCount = Object.create(null);
  if (WATCH.length) {
    const { installHook } = require('./instrument');
    globalThis.__rw = {
      w(name, p, op, loc, before, value, after) {
        if (inHook) return value;
        const n = mutCount[name] = (mutCount[name] || 0) + 1;
        if (n <= MUT_CAP) guarded(() => emit('mutation', { name, data: { path: p, op, loc, before, after: after ? read(after) : preview(value) } }));
        else if (n === MUT_CAP + 1) guarded(() => emit('mutation.capped', { name, data: { cap: MUT_CAP } }));
        return value;
      },
      get: read,
    };
    installHook(WATCH, msg => guarded(() => emit('instrument', msg)));
  }
  function preview(v) {
    if (typeof v === 'function') return `[Function ${v.name || 'anonymous'}]`;
    try { const s = JSON.stringify(v); return s === undefined ? String(v) : s.length > 200 ? s.slice(0, 199) + '…' : s; }
    catch { return Object.prototype.toString.call(v); }
  }
  function read(f) { try { return preview(f()); } catch (e) { return `[threw ${e && e.name}]`; } }

  // ---- lifecycle ---------------------------------------------------------------
  emit('run.start', { data: { run: process.env.REWIND_RUN_ID || null, argv: process.argv.slice(1).map(relFile), cwd: CWD,
    node: process.version, pid: process.pid, watch: WATCH, promise_stacks: PROMISE_STACKS } }, true);
  process.on('exit', code => {
    guarded(() => emit('run.end', { data: { code, mutations: mutCount, ast_loaded: Object.keys(require.cache).some(k => /[\\/]acorn[\\/]/.test(k)) } }));
    flush(); closed = true;
    try { fs.closeSync(fd); } catch {}
  });
  // Signals skip 'exit': flush, then re-raise with default behaviour.
  for (const sig of ['SIGINT', 'SIGTERM']) {
    process.once(sig, () => {
      guarded(() => emit('run.signal', { name: sig })); flush();
      if (process.listenerCount(sig) === 0) process.kill(process.pid, sig); // app has its own handler: leave it in charge
    });
  }
  globalThis.__rewind = { flush };
}
