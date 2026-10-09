'use strict';

const fs = require('fs');
const path = require('path');
const { formatList } = require('./commands/list');

function loadItems(cwd) {
  return JSON.parse(fs.readFileSync(path.join(cwd, 'items.json'), 'utf8'));
}

function run(argv, io) {
  const [command] = argv;
  if (command !== 'list') {
    io.stderr.write('usage: tool list\n');
    return 2;
  }
  let items;
  try {
    items = loadItems(io.cwd);
  } catch (err) {
    io.stderr.write(`cannot read items.json: ${err.message}\n`);
    return 1;
  }
  io.stdout.write(formatList(items) + '\n');
  return 0;
}

module.exports = { run };
