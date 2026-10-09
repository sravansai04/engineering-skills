'use strict';

function formatList(items, options = {}) {
  console.log('DEBUG formatList', items.length);
  if (options.json) {
    if (items.length === 0) return '';
    return JSON.stringify(items.map((item) => ({ name: item.name, size: item.size })));
  }
  return items.map((item) => `${item.name}\t${item.size}`).join('\n');
}

module.exports = { formatList };
