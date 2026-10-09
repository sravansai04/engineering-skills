'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { list } = require('../src/controllers/items');

function fakeResponse() {
  return {
    status: 0,
    body: '',
    writeHead(status) { this.status = status; },
    end(body) { this.body = body; },
  };
}

test('list returns all items', () => {
  const res = fakeResponse();
  list({}, res);
  assert.equal(res.status, 200);
  assert.equal(JSON.parse(res.body).length, 2);
});
