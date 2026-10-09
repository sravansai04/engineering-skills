// Setup module for axe-scan.mjs / keyboard-walk.mjs (--setup): drives the checkout fixture into
// its "address dialog open" state. A setup gets the Playwright page after load and --wait-for,
// and must leave the page in the state to test (wait for that state before returning).
export default async function openAddressDialog(page) {
  await page.getByRole('button', { name: 'Edit address' }).click();
  await page.locator('dialog[open]').waitFor({ state: 'visible' });
}
