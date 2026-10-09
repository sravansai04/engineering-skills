// Setup module (--setup): submits the checkout form with an empty email to reach the
// validation-error state. It submits with Enter from the email field because the fixed cookie
// banner covers "Place order" (one of the planted defects), so a mouse click cannot reach it.
export default async function submitEmpty(page) {
  await page.getByLabel('Email').press('Enter');
  await page.locator('#email.invalid').waitFor();
}
