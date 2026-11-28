// S1c: async functions that `return p` vs `return await p`.
function slow(tag) { return new Promise(r => setTimeout(function slowFire() { r(tag); }, 5)); } // @SLOW
async function viaReturn() { return slow('ret'); } // @VIARET
async function viaAwait() { return await slow('aw'); } // @VIAAW
(async function main() {
  console.log('got ' + await viaReturn()); // @CALLRET
  console.log('got ' + await viaAwait()); // @CALLAW
})();
