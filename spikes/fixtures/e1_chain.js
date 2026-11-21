const fs = require('fs');
function stepA() { setTimeout(function stepB() { fs.readFile(__filename, function stepC() { setTimeout(function stepD() { console.log('leaf'); }, 1); }); }, 1); }
stepA();
// unrelated sibling branch
setTimeout(function other() { console.log('other'); }, 5);
