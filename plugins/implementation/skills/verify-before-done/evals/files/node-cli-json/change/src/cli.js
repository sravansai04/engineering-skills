'use strict';

const fs = require('fs');
const path = require('path');
const { formatList } = require('./commands/list');

function loadItems(cwd) {
  return JSON.parse(fs.readFileSync(path.join(cwd, 'items.json'), 'utf8'));
}

function run(argv, io) {
  const [command, ...rest] = argv;
  if (command !== 'list') {
    io.stderr.write('usage: tool list [--json]\n');
    return 2;
  }
  const json = rest.includes('--json');
  let items;
  try {
    items = loadItems(io.cwd);
  } catch (err) {
    io.stderr.write(`cannot read items.json: ${err.message}\n`);
    return 1;
  }
  io.stdout.write(formatList(items, { json }) + '\n');
  return 0;
}

module.exports = { run };
