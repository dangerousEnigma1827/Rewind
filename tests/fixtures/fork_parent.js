// A parent that forks a child. fork() passes the parent's execArgv (--require recorder.js) and env to the child.
const { fork } = require('child_process');
if (process.argv[2] === 'child') {
  console.log(`child ran with ${process.execArgv.join(' ')}`);
  setTimeout(() => console.log('child done'), 20);
} else {
  console.log('parent before');
  fork(__filename, ['child']).on('exit', code => console.log(`parent after, child exit ${code}`));
}
