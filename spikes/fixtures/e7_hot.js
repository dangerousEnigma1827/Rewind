let currentCart = { items: [{ price: 1 }] }, other = { items: [{ price: 1 }] };
function reprice(i) { currentCart.items[i].price = i; }
function untouched(i) { other.items[i].price = i; }
let t = Date.now(); for (let i = 0; i < (+process.env.N||1e6); i++) untouched(0); const a = Date.now() - t;
t = Date.now(); for (let i = 0; i < (+process.env.N||1e6); i++) reprice(0); const b = Date.now() - t;
process.stderr.write(`HOT unwatched=${a}ms watched=${b}ms per_write=${(b * 1000 / (+process.env.N||1e6)).toFixed(2)}us\n`);
