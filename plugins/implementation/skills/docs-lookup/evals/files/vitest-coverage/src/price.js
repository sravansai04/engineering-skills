export function applyDiscount(cents, percent) {
  if (percent < 0 || percent > 100) throw new RangeError('percent out of range');
  return Math.round(cents * (1 - percent / 100));
}
