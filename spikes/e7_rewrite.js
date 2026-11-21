// E7 approach 1: AST rewrite of writes to watched module-level bindings (CJS only).
'use strict';
const Module = require('module'), acorn = require('acorn'), walk = require('acorn-walk'), MagicString = require('magic-string').default || require('magic-string');
const WATCH = new Set((process.env.REWIND_WATCH || '').split(',').filter(Boolean));
const MUT_METHODS = new Set(['push', 'pop', 'shift', 'unshift', 'splice', 'sort', 'reverse', 'fill', 'copyWithin', 'set', 'delete', 'clear', 'add']);
const log = [];
const preview = v => { try { const s = JSON.stringify(v); return s === undefined ? String(v) : s.slice(0, 200); } catch { return Object.prototype.toString.call(v); } };
globalThis.__rw = {
  // value = the expression's own result (returned unchanged); after = re-read of the target when safe
  w(name, path, op, loc, before, value, after) { log.push({ name, path, op, loc, before, after: after ? __rw.get(after) : preview(value) }); return value; },
  get(f) { try { return preview(f()); } catch { return undefined; } },
};
process.on('exit', () => process.stdout.write('MUTATIONS ' + JSON.stringify(log) + '\n'));

function rootAndPath(node, src) { // returns {root, path, pure} for Identifier / MemberExpression chains
  let path = [], pure = true;
  while (node.type === 'MemberExpression') {
    if (node.computed) { path.unshift('[' + src.slice(node.property.start, node.property.end) + ']'); if (!['Identifier', 'Literal'].includes(node.property.type)) pure = false; }
    else path.unshift('.' + node.property.name);
    node = node.object;
  }
  return node.type === 'Identifier' ? { root: node.name, path: path.join(''), pure } : null;
}
// Is `name` declared in a scope other than Program at this ancestor chain? (shadowing check)
function shadowed(name, ancestors) {
  for (let i = ancestors.length - 2; i >= 0; i--) {
    const a = ancestors[i];
    if (a.type === 'Program') return false;
    const decls = [];
    if (/Function/.test(a.type)) a.params.forEach(p => p.type === 'Identifier' && decls.push(p.name));
    if (a.type === 'BlockStatement' || /Function/.test(a.type)) {
      const body = a.type === 'BlockStatement' ? a.body : (a.body.body || []);
      for (const s of body) if (s.type === 'VariableDeclaration') s.declarations.forEach(d => d.id.type === 'Identifier' && decls.push(d.id.name));
    }
    if (decls.includes(name)) return true;
  }
  return false;
}
function instrument(src, file) {
  // shortcut: CJS wrapper means top-level `return` is legal
  const ast = acorn.parse(src, { ecmaVersion: 'latest', sourceType: 'script', allowReturnOutsideFunction: true, locations: true, allowHashBang: true });
  const ms = new MagicString(src);
  const loc = n => `${require('path').basename(file)}:${n.loc.start.line}:${n.loc.start.column + 1}`;
  const wrap = (n, target, op) => {
    const rp = rootAndPath(target, src);
    if (!rp || !WATCH.has(rp.root)) return;
    const tsrc = src.slice(target.start, target.end);
    // before-value only when re-evaluating the target has no side effects
    const reread = rp.pure ? `()=>${tsrc}` : 'null';
    const before = rp.pure ? `__rw.get(${reread})` : 'undefined';
    ms.prependLeft(n.start, `__rw.w(${JSON.stringify(rp.root)},${JSON.stringify(rp.path)},${JSON.stringify(op)},${JSON.stringify(loc(n))},${before},`);
    ms.appendRight(n.end, `,${reread})`);
  };
  walk.ancestor(ast, {
    AssignmentExpression(n, _, anc) { const rp = rootAndPath(n.left, src); if (rp && !shadowed(rp.root, anc)) wrap(n, n.left, n.operator); },
    UpdateExpression(n, _, anc) { const rp = rootAndPath(n.argument, src); if (rp && !shadowed(rp.root, anc)) wrap(n, n.argument, n.operator); },
    UnaryExpression(n, _, anc) { if (n.operator !== 'delete') return; const rp = rootAndPath(n.argument, src); if (rp && !shadowed(rp.root, anc)) wrap(n, n.argument, 'delete'); },
    CallExpression(n, _, anc) {
      if (n.callee.type !== 'MemberExpression' || n.callee.computed || !MUT_METHODS.has(n.callee.property.name)) return;
      const rp = rootAndPath(n.callee.object, src); if (rp && !shadowed(rp.root, anc)) wrap(n, n.callee.object, '.' + n.callee.property.name + '()');
    },
  });
  return ms.toString();
}
const orig = Module.prototype._compile;
Module.prototype._compile = function (content, filename) {
  if (WATCH.size && !filename.includes('node_modules') && !filename.startsWith(__dirname + require('path').sep + 'e7_')) {
    try { content = instrument(content, filename); } catch (e) { process.stderr.write(`rewind: could not instrument ${filename}: ${e.message}\n`); }
  }
  return orig.call(this, content, filename);
};
