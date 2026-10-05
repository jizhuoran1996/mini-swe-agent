'use strict';
// Standalone consumer source. The same file is materialised by solution/main.py at
// /workspace/consumer/consume.js and executed there, outside the source tree.
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const coreDir = process.env.SWC_INSTALL_ROOT;
assert(coreDir, 'SWC_INSTALL_ROOT not set');
const entry = path.join(coreDir, 'index.js');
assert(fs.existsSync(entry), 'missing bundle entry ' + entry);

const natives = fs.readdirSync(coreDir).filter((f) => f.endsWith('.node'));
assert(natives.length > 0, 'no freshly built .node binding in install root');
const nativePath = path.join(coreDir, natives[0]);

const swc = require(entry);
const resolved = require.resolve(entry);
assert(resolved.startsWith(fs.realpathSync(coreDir)), 'entry escaped install root: ' + resolved);

const source = [
  'export type Box<T> = { value: T };',
  'export const make = <T>(value: T): Box<T> => ({ value });',
  'export const n: number = make(41).value + 1;',
].join('\n');

const out = swc.transformSync(source, {
  filename: 'sample.ts',
  sourceMaps: true,
  jsc: { parser: { syntax: 'typescript' }, target: 'es2018' },
  module: { type: 'commonjs' },
});
assert.strictEqual(typeof out.code, 'string', 'code must be a string');
assert.ok(/exports|Object\.defineProperty/.test(out.code), 'commonjs emit missing');
assert.ok(out.map && typeof out.map.mappings === 'string' && out.map.mappings.length > 0,
  'source map mappings missing');

const Module = require('module');
const m = new Module('emitted', module);
m.filename = path.join(coreDir, 'emitted.js');
m.paths = Module._nodeModulePaths(coreDir);
m._compile(out.code, m.filename);
assert.strictEqual(m.exports.n, 42, 'transpiled runtime semantics wrong');

let threw = false;
try {
  swc.transformSync('const = ;', { filename: 'bad.ts', jsc: { parser: { syntax: 'typescript' } } });
} catch (e) { threw = true; }
assert.ok(threw, 'invalid syntax must raise a diagnostic');

const min = swc.minifySync('function add(a, b) { return a + b; }', { compress: true, mangle: false });
assert.ok(min.code && min.code.length > 0, 'minify produced no output');

console.log(JSON.stringify({
  core: entry,
  native: nativePath,
  native_sha256: crypto.createHash('sha256').update(fs.readFileSync(nativePath)).digest('hex'),
  mappings: out.map.mappings.length,
  value: m.exports.n,
  minified: min.code,
}));
