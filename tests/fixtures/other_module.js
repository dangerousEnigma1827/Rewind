// declares no top-level currentCart: writes to a same-named global must not be instrumented here
module.exports = function touch(o) { o.currentCart = 1; };
