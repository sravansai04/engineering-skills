'use strict';

const routes = require('./routes');

function handle(req, res) {
  const { pathname } = new URL(req.url, 'http://localhost');
  const handler = routes[`${req.method} ${pathname}`];
  if (!handler) {
    res.writeHead(404, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: 'not found' }));
    return;
  }
  handler(req, res);
}

module.exports = { handle };
