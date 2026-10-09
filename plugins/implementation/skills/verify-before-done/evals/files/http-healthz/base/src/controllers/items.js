'use strict';

const ITEMS = [
  { id: 1, name: 'alpha' },
  { id: 2, name: 'beta' },
];

function list(req, res) {
  res.writeHead(200, { 'content-type': 'application/json' });
  res.end(JSON.stringify(ITEMS));
}

module.exports = { list };
