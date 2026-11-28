// S1f: awaiting a non-native thenable that settles from a timer.
const thenable = { then(res) { setTimeout(function thenableFire() { res(7); }, 5); } }; // @THENABLE
(async function main() {
  const v = await thenable; // @AWAIT
  console.log('thenable ' + v);
})();
