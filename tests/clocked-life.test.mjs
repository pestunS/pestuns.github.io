import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

// Exercise the same board evolution, pulse layout and probes as the standalone page.
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const source = ['life-core', 'clocked-eq'].map(id =>
  html.match(new RegExp('<script id="' + id + '">([\\s\\S]*?)</script>'))[1]
).join('\n');
const { evolve, eqCircuit, cellKey } = vm.runInNewContext(source + '\n({ evolve, eqCircuit, cellKey })');

function seed(a, b) {
  const board = new Set();
  eqCircuit.seed(a, b, (x, y) => board.add(cellKey(x, y)));
  return board;
}

function advance(board, steps) {
  for (let i = 0; i < steps; i++) board = evolve(board);
  return board;
}

test('every pair of four-bit streams passes through the same two gates', () => {
  const word = n => n.toString(2).padStart(4, '0');
  for (let i = 0; i < 16; i++) for (let j = 0; j < 16; j++) {
    const a = word(i), b = word(j);
    let board = seed(a, b);
    const events = [];
    for (let k = 0; k < 4; k++) for (const port of ['a', 'b', 'eq', 'not']) {
      const tick = eqCircuit.ports[port].tick + k * eqCircuit.period;
      events.push({ tick, port, slot: k });
    }
    let previous = 0;
    for (const { tick, port, slot } of events.sort((p, q) => p.tick - q.tick)) {
      board = advance(board, tick - previous);
      previous = tick;
      const equal = a[slot] === b[slot];
      const expected = { a: a[slot], b: b[slot], eq: equal, not: !equal };
      assert.equal(eqCircuit.read(port, board), Number(expected[port]),
        `${a}/${b}, slot ${slot + 1}, ${port} at generation ${tick}`);
    }
  }
});

test('cutting the EQ pulse changes the downstream NOT result', () => {
  const { eq, not } = eqCircuit.ports;
  const atEQ = advance(seed('0011', '0101'), eq.tick);
  assert.equal(eqCircuit.read('eq', atEQ), 1);
  const cut = new Set(atEQ);
  for (const [x, y] of eq.cells) cut.delete(cellKey(x, y));
  const delay = not.tick - eq.tick;
  assert.equal(eqCircuit.read('not', advance(atEQ, delay)), 0);
  assert.equal(eqCircuit.read('not', advance(cut, delay)), 1);
});

test('a glider keeps travelling across the viewport edge at negative world coordinates', () => {
  const offsets = [[1, 0], [2, 1], [0, 2], [1, 2], [2, 2]];
  const glider = distance => new Set(offsets.map(([x, y]) => cellKey(96 + x + distance, -6 + y + distance)));
  assert.deepEqual([...advance(glider(0), 40)].sort(), [...glider(10)].sort());
});
