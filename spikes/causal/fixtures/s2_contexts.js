// S2a: the eid recorded on async.init vs executionAsyncId() read by user code at the same moment.
const { executionAsyncId: ctx } = require('async_hooks');
function make(where) { console.log(`ctx ${where} ${ctx()}`); return new Promise(r => r(where)); } // @MAKE
make('top');
new Promise(r => { make('executor'); r(); });
Promise.resolve().then(function inThen() { make('then'); });
setTimeout(function inTimer() { make('timer'); }, 1);
setImmediate(function inImmediate() { make('immediate'); });
process.nextTick(function inTick() { make('tick'); });
queueMicrotask(function inMicrotask() { make('microtask'); });
(async function inAsync() { await null; make('after-await'); })();
