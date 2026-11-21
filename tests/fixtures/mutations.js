let currentCart = null;
function load(id) { currentCart = { id, items: [{ price: 10 }] }; }
function addItem(p) { currentCart.items.push({ price: p }); }
function reprice(i) { currentCart.items[i].price = 99; }
function bump() { currentCart.id++; }
function strip() { delete currentCart.items; }
function alias() { const c = currentCart; c.coupon = 'X'; }
function shadow() { let currentCart = {}; currentCart.local = 1; }
function compound() { currentCart.total = (currentCart.total || 0) + 5; }
function sideEffectKey() { let k = 0; currentCart.items[k++] = 1; return k; }
function destructure() { [currentCart.d] = [7]; }
let other = { n: 0 }; other.n = 1;
load(1); addItem(5); reprice(0); bump(); compound(); alias(); shadow(); destructure();
if (sideEffectKey() !== 1) throw new Error('key evaluated twice');
strip();
setTimeout(function boom() { currentCart.items[0].price; }, 1);
