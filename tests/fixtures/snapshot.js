// Error-time snapshots of watched variables (--watch currentCart,count,circular,trap,big).
let currentCart = { order: 'A', items: [1] };
let count = 0;
let circular = {}; circular.self = circular;              // JSON can't serialise it
let trap = { get boom() { throw new Error('getter'); } }; // serialising it throws
let big = 10n;                                            // JSON can't serialise BigInt
function setCart(o) { currentCart = o; }                  // recorded write
function sneaky() { const c = currentCart; c.order = 'Z'; } // write through an alias: not recorded
setCart({ order: 'B', items: [1, 2] });
count++;
sneaky();
if (process.env.SNAP_TWICE) { // two uncaught errors, each with its own snapshot
  process.on('uncaughtException', e => console.log('handled ' + e.message));
  setTimeout(function first() { count = 10; throw new Error('first'); }, 1);
  setTimeout(function second() { count = 20; throw new Error('second'); }, 20);
} else {
  setTimeout(function boom() { currentCart.items[5].x; }, 1);
}
