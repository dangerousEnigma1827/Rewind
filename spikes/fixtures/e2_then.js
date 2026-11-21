function scheduleIt() { Promise.resolve(1).then(function boom() { null.x; }); }
setTimeout(scheduleIt, 1);
