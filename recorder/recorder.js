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
  const READS = process.env.REWIND_READS !== '0';         // record reads of watched names (with --watch)
  const READ_CAP = +process.env.REWIND_READ_CAP || 10000; // per watched name, after per-callback dedupe
  const readSeen = new Set(); // read locations already recorded in the current callback run
  const HERE = __dirname;
  const CWD = process.cwd();

  const fd = fs.openSync(OUT, 'w');
  // This process now owns the file. Child processes inherit env, and fork()/cluster also inherit execArgv
  // (--require recorder.js); without this their recorder would reopen OUT with 'w' and corrupt this recording.
  // Children stay unrecorded (documented), and the preload is inert in them.
  delete process.env.REWIND_OUT;
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
    return ev.seq;
  }
  function flush() {
    if (!buf.length || closed) return;
    const s = buf.join('\n') + '\n'; buf = [];
    try { fs.writeSync(fd, s); } catch { /* disk full / fd gone: nothing safe left to do */ }
  }
  // Every recorder entry point runs under this guard so its own work is never recorded.
  function guarded(fn) { if (inHook) return; inHook = true; try { fn(); } finally { inHook = false; } }

  // ---- async lifecycle ------------------------------------------------------
  const timerAid = new WeakMap(); // Timeout/Immediate object -> aid, so a clear can name what it cancelled
  ah.createHook({
    init(aid, type, tid, res) {
      if ((type === 'Timeout' || type === 'Immediate') && res) timerAid.set(res, aid);
      guarded(() => {
        const cb = res && (res._onTimeout || res._onImmediate);
        emit('async.init', { aid, tid, type, name: cb ? (cb.name || '<anonymous>') : null,
          stack: type !== 'PROMISE' || PROMISE_STACKS ? callsites() : null,
          ...(type === 'Timeout' && res ? { data: { delay: res._idleTimeout } } : {}) }); // due time: overdue vs not yet due
      });
    },
    before(aid) { if (readSeen.size) readSeen.clear(); guarded(() => emit('async.before', { aid })); },
    after(aid) { guarded(() => emit('async.after', { aid })); },
    promiseResolve(aid) { guarded(() => emit('async.resolve', { aid })); },
  }).enable();

  // A cleared timer never fires, which would otherwise look exactly like one still pending when the run ended.
  // shortcut: clears by numeric id (`clearTimeout(+t)`) and AbortSignal-cancelled timers/promises aren't seen; add if needed.
  const timers = require('timers');
  for (const name of ['clearTimeout', 'clearInterval', 'clearImmediate']) {
    const orig = timers[name];
    const patched = function (t) {
      const aid = t && typeof t === 'object' ? timerAid.get(t) : undefined;
      if (aid !== undefined) guarded(() => emit('async.cancel', { aid }));
      return orig.apply(this, arguments);
    };
    timers[name] = patched;
    if (globalThis[name] === orig) globalThis[name] = patched;
  }

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
    let finished = false;
    // `finish` below runs in the request's scope, so it can't say which callback sent the response. The first
    // end() call can: its eid is the calling callback, and its stack is the user code that called it (or empty,
    // when Node internals such as stream.pipe end it). Measured cost: not detectable (spikes/causal S5).
    const origEnd = res.end;
    let endSeen = false;
    res.end = function () {
      if (!endSeen) {
        endSeen = true;
        guarded(() => emit('http.end', { name: `${req.method} ${req.url}`, data: { req: id }, stack: callsites() }));
      }
      return origEnd.apply(this, arguments);
    };
    res.once('finish', () => { finished = true; guarded(() => emit('http.out', { name: `${res.statusCode} ${req.method} ${req.url}`,
      data: { req: id, status: res.statusCode, ms: Number(process.hrtime.bigint() - start) / 1e6 } }, res.statusCode >= 500)); });
    // connection closed before the response finished: the client gave up (or the socket died), not a stall
    res.once('close', () => { if (!finished) guarded(() => emit('http.abort', { name: `${req.method} ${req.url}`,
      data: { req: id, ms: Number(process.hrtime.bigint() - start) / 1e6 } })); });
    const args = arguments;
    return anchor.runInAsyncScope(() => {
      guarded(() => emit('http.in', { aid: anchor.asyncId(), name: `${req.method} ${req.url}`, data: { req: id, method: req.method, url: req.url } }));
      return origEmit.apply(this, args);
    });
  };

  // ---- errors ------------------------------------------------------------------
  // Monitor only: observes without changing crash semantics or exit codes (E2/E3).
  process.on('uncaughtExceptionMonitor', (err, origin) => {
    guarded(() => {
      const at = emit('error.uncaught', { name: errInfo(err).message, data: { origin, ...errInfo(err) }, stack: parseStack(err && err.stack) }, true);
      // --watch: the watched variables' values at this moment, tied to this error by its seq
      let values = null;
      try { values = globalThis.__rw && globalThis.__rw.snapshot(); } catch { /* never let a snapshot change the crash */ }
      if (values && values.length) emit('snapshot', { name: 'uncaught error', data: { error: at, values } }, true);
    });
  });

  // ---- source identity ----------------------------------------------------------
  // Hash each user CommonJS file as Node loads it, so ingest can prove its source snapshot is the code that ran.
  const Module = require('module');
  const crypto = require('crypto');
  const origCompile = Module.prototype._compile;
  Module.prototype._compile = function (content, filename) {
    if (typeof filename === 'string' && keepFile(filename) && !filename.includes(`${path.sep}node_modules${path.sep}`)) {
      guarded(() => {
        let sha256 = null;
        try { sha256 = crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex'); } catch { /* unreadable: ingest reports it */ }
        emit('source', { name: relFile(filename), data: { sha256 } });
      });
    }
    return origCompile.apply(this, arguments);
  };

  // ---- mutation tracking (opt-in; AST deps loaded only here) -------------------
  const mutCount = Object.create(null), readCount = Object.create(null);
  if (WATCH.length) {
    const { installHook } = require('./instrument');
    const registry = []; // [file, {name: getter}] per instrumented file, registered when its module body finishes
    globalThis.__rw = {
      reg(file, getters) { registry.push([file, getters]); },
      snapshot() { // read() never throws: TDZ, throwing getters/toJSON and unserialisable values become text
        const out = [];
        for (const [file, getters] of registry) for (const name of Object.keys(getters)) out.push({ name, file, value: read(getters[name]) });
        return out;
      },
      w(name, p, op, loc, before, value, after) {
        if (inHook) return value;
        const n = mutCount[name] = (mutCount[name] || 0) + 1;
        if (n <= MUT_CAP) guarded(() => emit('mutation', { name, data: { path: p, op, loc, before, after: after ? read(after) : preview(value) } }));
        else if (n === MUT_CAP + 1) guarded(() => emit('mutation.capped', { name, data: { cap: MUT_CAP } }));
        return value;
      },
      // A read is recorded once per source location per callback run (a hot loop emits one event, not N).
      r(name, loc, value) {
        if (inHook || readSeen.has(loc)) return value;
        readSeen.add(loc);
        const n = readCount[name] = (readCount[name] || 0) + 1;
        if (n <= READ_CAP) guarded(() => emit('read', { name, data: { loc, value: read(() => value) } }));
        else if (n === READ_CAP + 1) guarded(() => emit('read.capped', { name, data: { cap: READ_CAP } }));
        return value;
      },
      get: read,
    };
    installHook(WATCH, msg => guarded(() => emit('instrument', msg)), { reads: READS });
  }
  function preview(v) {
    if (typeof v === 'function') return `[Function ${v.name || 'anonymous'}]`;
    try { const s = JSON.stringify(v); return s === undefined ? String(v) : s.length > 200 ? s.slice(0, 199) + '…' : s; }
    catch { // circular, BigInt, throwing getter/toJSON; the tag lookup itself can throw on a hostile Proxy
      let tag = 'value';
      try { tag = Object.prototype.toString.call(v).slice(8, -1); } catch { }
      return `[unserialisable ${tag}]`;
    }
  }
  function read(f) { try { return preview(f()); } catch (e) { return `[threw ${e && e.name}]`; } }

  // ---- lifecycle ---------------------------------------------------------------
  emit('run.start', { data: { run: process.env.REWIND_RUN_ID || null, argv: process.argv.slice(1).map(relFile), cwd: CWD,
    node: process.version, pid: process.pid, watch: WATCH, reads: WATCH.length > 0 && READS, promise_stacks: PROMISE_STACKS } }, true);
  process.on('exit', code => {
    guarded(() => emit('run.end', { data: { code, mutations: mutCount, reads: readCount, ast_loaded: Object.keys(require.cache).some(k => /[\\/]acorn[\\/]/.test(k)) } }));
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
