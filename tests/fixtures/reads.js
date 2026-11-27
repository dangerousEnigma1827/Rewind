let cart = { items: [{ price: 3 }, { price: 4 }], total: 0 };
class Box { constructor(v) { this.v = v; } }
let Ctor = Box;
function total() { let t = 0; for (let i = 0; i < cart.items.length; i++) t += cart.items[i].price; return t; }
function shadow() { const cart = { items: [] }; return cart.items.length; }
function wrapCart() { return { cart }; }
const b = new Ctor(1);
cart.total = total();
cart.total = cart.total + 1;
delete cart.total;
const kind = typeof cart;
const w = wrapCart();
console.log(JSON.stringify([total(), shadow(), w.cart === cart, b.v, kind]));
setTimeout(function later() { console.log(String(cart.items.length)); }, 1);
