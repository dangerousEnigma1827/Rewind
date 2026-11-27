// A program that never exits on its own: for stopping a recording from the TUI.
let ticks = 0;
console.log('started');
setInterval(() => { ticks++; if (ticks % 10 === 0) console.log(`tick ${ticks}`); }, 20);
