// cluster primary with one worker; cluster.fork() inherits execArgv (--require recorder.js) and env.
const cluster = require('cluster');
if (cluster.isPrimary) {
  console.log('primary before');
  cluster.fork().on('exit', code => console.log(`primary after, worker exit ${code}`));
} else {
  console.log('worker ran');
  process.exit(0);
}
