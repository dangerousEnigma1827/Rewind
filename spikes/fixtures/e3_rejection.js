async function handler() { await new Promise(r => setTimeout(r, 2)); throw new Error('rejected'); }
setTimeout(function root() { handler(); }, 1);
