// S1b: outer is resolved WITH a still-pending inner promise (adoption). When does outer's async.resolve fire?
const inner = new Promise(r => setTimeout(function innerFire() { r('v'); }, 20)); // @INNER
const outer = new Promise(r => setTimeout(function outerFire() { r(inner); }, 2)); // @OUTER
outer.then(function cont(v) { console.log('cont ' + v); }); // @THEN
