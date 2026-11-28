// S1a: a promise settled by a timer; does async.resolve fire inside the timer callback?
async function main() {
  const p = new Promise(r => setTimeout(function fire() { r(1); }, 5)); // @P
  await p; // @AWAIT
  console.log('after await');
}
main();
