'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { healthz } = require('../src/controllers/health');

test('healthz reports ok', () => {
  const res = {
    status: 0,
    body: '',
    writeHead(status) { this.status = status; },
    end(body) { this.body = body; },
  };
  healthz({}, res);
  assert.equal(res.status, 200);
  assert.deepEqual(JSON.parse(res.body), { status: 'ok' });
});
