// A then-callback returns a non-native thenable. Node runs the thenable's then() as a SECOND run of the same
// promise reaction: that run wasn't released by the parent promise, and must not be reported as if it were.
Promise.resolve().then(function first() {
  return { then(r) { console.log('inside thenable'); setTimeout(function later() { r(1); }, 5); } };
}).then(function second(v) { console.log('done ' + v); });
