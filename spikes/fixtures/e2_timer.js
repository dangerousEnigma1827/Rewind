function scheduleIt() { setTimeout(function boom() { null.x; }, 1); }
setTimeout(function unrelated() {}, 0);
scheduleIt();
