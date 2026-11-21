// E7 approach 2: in-process inspector, conditional breakpoint that records and returns false (never pauses).
'use strict';
const inspector = require('inspector');
const [file, line, expr] = process.env.RW_LP.split('|');   // e.g. "e7_hot.js|2|currentCart.items[i].price"
const hits = [];
globalThis.__rwSnap = (v) => { hits.push(JSON.stringify(v)); return false; };
const s = new inspector.Session(); s.connect();
let sync = false;
s.post('Debugger.enable', () => { sync = true; });
const syncEnable = sync;
s.post('Debugger.setBreakpointByUrl', { lineNumber: +line - 1, urlRegex: file.replace('.', '\.') + '$',
  condition: `globalThis.__rwSnap(${expr})` }, (err, r) => { if (err) console.error('bp err', err); else process.stderr.write(`BP set, locations now=${r.locations.length}, sync_callbacks=${syncEnable}\n`); });
s.on('Debugger.paused', () => { process.stderr.write('PAUSED (bad)\n'); s.post('Debugger.resume'); });
process.on('exit', () => process.stderr.write(`LOGPOINT hits=${hits.length} first=${hits[0]} last=${hits[hits.length - 1]}\n`));
