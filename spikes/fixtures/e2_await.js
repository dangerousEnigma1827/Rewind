const fs = require('fs/promises');
async function scheduleIt() { await fs.readFile(__filename); null.x; }
setTimeout(function outer() { scheduleIt(); }, 1);
