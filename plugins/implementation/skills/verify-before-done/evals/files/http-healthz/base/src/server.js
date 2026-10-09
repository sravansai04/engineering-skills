'use strict';

const http = require('http');
const { handle } = require('./app');

const port = Number(process.env.PORT || 3000);

http.createServer(handle).listen(port, () => {
  console.error(`listening on http://localhost:${port}`);
});
