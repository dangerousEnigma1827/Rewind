// request-like root -> await fs -> await timer -> log ; two concurrent "requests" must stay separated
const fsp = require('fs/promises');
const { setTimeout: sleep } = require('timers/promises');
async function handler(id) { await fsp.readFile(__filename); await sleep(id * 3); console.log('done ' + id); }
setTimeout(function req1() { handler(1); }, 1);
setTimeout(function req2() { handler(2); }, 1);
