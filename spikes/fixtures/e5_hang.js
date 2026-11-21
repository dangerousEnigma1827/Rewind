// keeps running; parent SIGKILLs it
let n = 0; setInterval(() => { console.log('tick', n++); }, 5);
