// State reconstruction (--watch cart,count,untouched): whole writes, repeated writes, interleaved timers, a read,
// a property write, an alias write the recorder can't see, and a later read that reveals it.
let cart = null;
let count = 0;
let untouched = 'declared, never read or written again';
function put(v) { cart = v; }
put({ id: 1 });
count++;
count++;
setTimeout(function a() { put({ id: 2 }); console.log('a done'); }, 10);
setTimeout(function b() { console.log('b saw ' + cart.id); }, 20);
setTimeout(function c() { cart.items = [1]; console.log('c done'); }, 30);
setTimeout(function d() { const alias = cart; alias.id = 99; console.log('d done'); }, 40);
setTimeout(function e() { console.log('e saw ' + JSON.stringify(cart)); }, 50);
if (process.env.STATE_HOLD) setTimeout(() => { console.error(new Error('holding')); setInterval(() => {}, 1000); }, 60);
