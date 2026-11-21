const fs = require('fs');
function scheduleIt() { fs.readFile(__filename, function boom() { null.x; }); }
scheduleIt();
