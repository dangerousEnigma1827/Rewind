// S1e: a promise rejected inside a timer and awaited under try/catch. Does async.resolve fire for a rejection?
(async function main() {
  const p = new Promise((_, rej) => setTimeout(function failLater() { rej(new Error('boom')); }, 5)); // @P
  try { await p; } catch (e) { console.log('caught ' + e.message); } // @AWAIT
})();
