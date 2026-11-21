// E7 approach 3: deep Proxy on an opt-in tracked object. Catches alias writes; cannot see `let` reassignment.
const log = [];
function track(obj, name, path = '') {
  if (obj === null || typeof obj !== 'object') return obj;
  return new Proxy(obj, {
    get(t, k, r) { const v = Reflect.get(t, k, r); return typeof k === 'string' && v && typeof v === 'object' ? track(v, name, path + '.' + k) : v; },
    set(t, k, v, r) { log.push({ name, path: path + '.' + String(k), op: '=', after: JSON.stringify(v) }); return Reflect.set(t, k, v, r); },
    deleteProperty(t, k) { log.push({ name, path: path + '.' + String(k), op: 'delete' }); return Reflect.deleteProperty(t, k); },
  });
}
let cart = track({ items: [{ price: 10 }] }, 'cart');
const alias = cart; alias.coupon = 'X';          // alias write
cart.items.push({ price: 5 });                   // push -> set [1] + set length
cart.items[0].price = 1;
cart = { items: [] };                            // reassignment: invisible
const t = Date.now(); const p = track({ a: { b: 0 } }, 'p'); for (let i = 0; i < 1e6; i++) p.a.b = i;
console.log(JSON.stringify(log.slice(0, 5)), 'total', log.length, 'hot_ms', Date.now() - t);
console.log('ALIAS_CAUGHT', log.some(l => l.path === '.coupon'), 'REASSIGN_CAUGHT', log.some(l => l.path === ''));
