// thrown synchronously inside an async-hook callback of a request-like root, after an await on timer
const { setTimeout: sleep } = require('timers/promises');
async function handler() { await sleep(2); throw new Error('after-await'); }
setTimeout(function root() { handler(); }, 1);
