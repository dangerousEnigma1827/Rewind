const fsp = require('fs/promises');
async function handler() { await fsp.readFile(__filename); throw new Error('rejected after await'); }
setTimeout(function root() { handler(); }, 1);
