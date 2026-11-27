// Reading a watched `let` before its declaration throws ReferenceError, with or without instrumentation.
try { console.log(late); } catch (e) { console.log(e.name); }
let late = 1;
