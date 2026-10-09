'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { formatList } = require('../src/commands/list');

const items = [
  { name: 'alpha', size: 3 },
  { name: 'beta', size: 5 },
];

test('text output lists one item per line', () => {
  assert.equal(formatList(items), 'alpha\t3\nbeta\t5');
});
