// S1g: a promise that settled long before anyone awaits it. The await must not look like a wait on it.
const done = new Promise(r => setTimeout(function early() { r('ready'); }, 1)); // @P
setTimeout(async function later() {
  const v = await done; // @AWAIT
  console.log('late ' + v);
}, 20);
