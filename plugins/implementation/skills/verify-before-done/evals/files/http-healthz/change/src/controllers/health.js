'use strict';

function healthz(req, res) {
  res.writeHead(200, { 'content-type': 'application/json' });
  res.end(JSON.stringify({ status: 'ok' }));
}

module.exports = { healthz };
