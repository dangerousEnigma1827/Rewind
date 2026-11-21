let currentCart = null;                                   // L1
function load(id) { currentCart = { id, items: [{ price: 10 }] }; }   // L2 reassign
function addItem(p) { currentCart.items.push({ price: p }); }        // L3 mutating call
function reprice(i) { currentCart.items[i].price = 99; }             // L4 computed member
function bump() { currentCart.id++; }                                // L5 update
function strip() { delete currentCart.items; }                       // L6 delete
function alias() { const c = currentCart; c.coupon = 'X'; }          // L7 alias write (expected MISS)
function shadow() { let currentCart = {}; currentCart.local = 1; }   // L8 shadowed local (must NOT record)
function compound() { currentCart.total = (currentCart.total || 0) + 5; } // L9
function sideEffectKey() { let k = 0; currentCart.items[k++] = 1; return k; } // L10 key must eval once
load(1); addItem(5); reprice(0); bump(); compound(); alias(); shadow();
if (sideEffectKey() !== 1) throw new Error('key evaluated twice');
strip();
if (process.env.HOT) { const t = Date.now(); for (let i = 0; i < +process.env.HOT; i++) reprice(0); process.stderr.write('HOT_MS ' + (Date.now() - t) + '\n'); }
setTimeout(function boom() { currentCart.items[0].price; }, 1);      // L15 throws: stack must say :15
