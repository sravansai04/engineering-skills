'use strict';

function formatList(items) {
  return items.map((item) => `${item.name}\t${item.size}`).join('\n');
}

module.exports = { formatList };
