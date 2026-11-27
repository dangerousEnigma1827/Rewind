// Mutation instrumentation for `rewind record --watch name[,name]`. Loaded only when --watch is used.
//
// Exactly what is captured (validated in spikes/RESULTS.md, E7):
//   syntactic writes to a watched binding that is declared at the top level of a CommonJS file:
//   `x = v`, `x.a = v`, `x[k] = v`, compound ops, `x++`/`--`, `delete x.a`, and calls to known mutating
//   methods on it (`x.items.push(v)`, ...).
// NOT captured: destructuring targets (`[x.a] = v`), writes through aliases (`const c = x; c.a = 1`), files in node_modules, ESM files,
//   mutations done inside functions the value is passed to, and same-named locals (deliberately skipped).
'use strict';
const Module = require('module');
const path = require('path');
const acorn = require('acorn');
const walk = require('acorn-walk');
const MagicString = require('magic-string').default || require('magic-string');

const MUT_METHODS = new Set(['push', 'pop', 'shift', 'unshift', 'splice', 'sort', 'reverse', 'fill', 'copyWithin',
  'set', 'delete', 'clear', 'add']);

function patternNames(p, out) {
  if (!p) return out;
  switch (p.type) {
    case 'Identifier': out.push(p.name); break;
    case 'ObjectPattern': p.properties.forEach(q => patternNames(q.type === 'RestElement' ? q.argument : q.value, out)); break;
    case 'ArrayPattern': p.elements.forEach(e => patternNames(e, out)); break;
    case 'RestElement': patternNames(p.argument, out); break;
    case 'AssignmentPattern': patternNames(p.left, out); break;
  }
  return out;
}
// Names declared directly in a scope node (not nested). `var` hoisting inside nested blocks is ignored:
// shortcut: function-scoped `var` declared in a nested block is not seen as shadowing; rare in practice.
function declaredIn(node) {
  const names = [];
  const stmts = node.type === 'Program' || node.type === 'BlockStatement' || node.type === 'StaticBlock' ? node.body
    : node.type === 'SwitchCase' ? node.consequent : [];
  for (const s of stmts) {
    if (s.type === 'VariableDeclaration') s.declarations.forEach(d => patternNames(d.id, names));
    else if ((s.type === 'FunctionDeclaration' || s.type === 'ClassDeclaration') && s.id) names.push(s.id.name);
  }
  if (/Function/.test(node.type)) { node.params.forEach(p => patternNames(p, names)); if (node.type === 'FunctionExpression' && node.id) names.push(node.id.name); }
  if (node.type === 'CatchClause') patternNames(node.param, names);
  if (/^For(In|Of)?Statement$/.test(node.type)) {
    const d = node.type === 'ForStatement' ? node.init : node.left;
    if (d && d.type === 'VariableDeclaration') d.declarations.forEach(x => patternNames(x.id, names));
  }
  return names;
}
function shadowed(name, ancestors) {
  for (let i = ancestors.length - 2; i >= 0; i--) {
    const a = ancestors[i];
    if (a.type === 'Program') return false;
    if (declaredIn(a).includes(name)) return true;
  }
  return false;
}
function rootAndPath(node, src) {
  const parts = []; let pure = true;
  while (node.type === 'MemberExpression' || node.type === 'ChainExpression') {
    if (node.type === 'ChainExpression') { node = node.expression; continue; }
    if (node.computed) {
      parts.unshift('[' + src.slice(node.property.start, node.property.end) + ']');
      if (node.property.type !== 'Identifier' && node.property.type !== 'Literal') pure = false; // re-reading would re-run side effects
    } else parts.unshift('.' + (node.property.name || node.property.value));
    node = node.object;
  }
  return node.type === 'Identifier' ? { root: node.name, node, path: parts.join(''), pure } : null;
}

function instrument(src, file, watch, { reads: withReads = true } = {}) {
  const ast = acorn.parse(src, { ecmaVersion: 'latest', sourceType: 'script', allowReturnOutsideFunction: true,
    allowHashBang: true, locations: true });
  const top = new Set(declaredIn(ast));
  const targets = new Set(watch.filter(w => top.has(w)));
  if (!targets.size) return { code: src, writes: 0, reads: 0, names: [] };
  const ms = new MagicString(src);
  const rel = path.relative(process.cwd(), file).split(path.sep).join('/');
  let writes = 0, reads = 0;
  const writeRoots = new Set(); // the identifier at the root of each wrapped write target: a write, not a read
  const wrap = (n, target, op, anc) => {
    const rp = rootAndPath(target, src);
    if (!rp || !targets.has(rp.root) || shadowed(rp.root, anc)) return;
    writeRoots.add(rp.node);
    const tsrc = src.slice(target.start, target.end);
    const reread = rp.pure ? `()=>(${tsrc})` : 'null';
    const before = rp.pure ? `__rw.get(${reread})` : 'undefined';
    const loc = `${rel}:${n.loc.start.line}:${n.loc.start.column + 1}`;
    // Same line, so stack-trace line numbers in user code are unchanged.
    ms.prependLeft(n.start, `__rw.w(${JSON.stringify(rp.root)},${JSON.stringify(rp.path)},${JSON.stringify(op)},${JSON.stringify(loc)},${before},(`);
    ms.appendRight(n.end, `),${reread})`);
    writes++;
  };
  walk.ancestor(ast, {
    AssignmentExpression(n, _, anc) { wrap(n, n.left, n.operator, anc); },
    UpdateExpression(n, _, anc) { wrap(n, n.argument, n.operator, anc); },
    UnaryExpression(n, _, anc) { if (n.operator === 'delete') wrap(n, n.argument, 'delete', anc); },
    CallExpression(n, _, anc) {
      const c = n.callee;
      if (c.type === 'MemberExpression' && !c.computed && MUT_METHODS.has(c.property.name)) wrap(n, c.object, `.${c.property.name}()`, anc);
    },
  });
  // Reads: every expression reference to a watched binding, wrapped as __rw.r(name, loc, x), which returns x.
  // acorn-walk visits declarations, params and assignment targets as patterns, never as `Identifier`, and skips
  // non-computed keys, so only real references arrive here. Write-target roots were wrapped above. The edits
  // use prependRight/appendLeft (writes use prependLeft/appendRight), so a read always nests inside a write.
  if (withReads) walk.ancestor(ast, {
    Identifier(n, _, anc) {
      if (!targets.has(n.name) || writeRoots.has(n) || shadowed(n.name, anc)) return;
      const parent = anc[anc.length - 2];
      if (parent && parent.type === 'UnaryExpression' && parent.operator === 'delete') return; // `delete x` isn't a read
      const call = `__rw.r(${JSON.stringify(n.name)},${JSON.stringify(`${rel}:${n.loc.start.line}:${n.loc.start.column + 1}`)},`;
      if (parent && parent.type === 'Property' && parent.shorthand && parent.value === n) {
        ms.prependRight(n.start, `${n.name}: ${call}`); ms.appendLeft(n.end, ')');      // {x} -> {x: __rw.r(..., x)}
      } else if (parent && parent.type === 'NewExpression' && parent.callee === n) {
        ms.prependRight(n.start, `(${call}`); ms.appendLeft(n.end, '))');               // new x() keeps its arguments
      } else {
        ms.prependRight(n.start, call); ms.appendLeft(n.end, ')');
      }
      reads++;
    },
  });
  // Getters for the error-time snapshot, on a new last line so no existing line or column moves. They run when the
  // module body finishes; an error thrown while it is still running finds this file not yet registered.
  ms.append(`\n;__rw.reg(${JSON.stringify(rel)},{${[...targets].map(t => `${JSON.stringify(t)}:()=>${t}`).join(',')}});`);
  return { code: ms.toString(), writes, reads, names: [...targets] };
}

function installHook(watch, report, opts) {
  const orig = Module.prototype._compile;
  Module.prototype._compile = function (content, filename) {
    if (!filename.includes(`${path.sep}node_modules${path.sep}`) && !filename.startsWith(__dirname)) {
      try {
        const r = instrument(content, filename, watch, opts);
        if (r.writes || r.reads) report({ name: 'instrumented', data: { file: path.relative(process.cwd(), filename).split(path.sep).join('/'), writes: r.writes, reads: r.reads, watch: r.names } });
        content = r.code;
      } catch (e) {
        report({ name: 'instrument_failed', data: { file: filename, error: e.message } }); // run uninstrumented rather than crash
      }
    }
    return orig.call(this, content, filename);
  };
}

module.exports = { installHook, instrument };
