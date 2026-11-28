// S1d: Promise.all / Promise.race over two timers of different length.
const t = (ms, tag) => new Promise(r => setTimeout(function tick() { r(tag); }, ms)); // @T
(async function main() {
  const all = await Promise.all([t(3, 'a'), t(12, 'b')]); // @ALL
  console.log('all ' + all.join(','));
  const first = await Promise.race([t(15, 'slow'), t(4, 'fast')]); // @RACE
  console.log('race ' + first);
})();
