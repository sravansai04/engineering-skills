'use strict';

const items = require('./controllers/items');

// Every route the service exposes: "METHOD /path" -> handler(req, res).
module.exports = {
  'GET /items': items.list,
};
