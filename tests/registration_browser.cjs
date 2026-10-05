// Run with Playwright available on NODE_PATH: node tests/registration_browser.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 360, height: 740 }, isMobile: true });
    const errors = [];
    const requests = [];
    let fail = true;
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      window.Telegram = { WebApp: {
        initData: 'signed-test-data', initDataUnsafe: { user: { id: 123, username: 'test' } },
        expand() {}, ready() {}, openTelegramLink(link) { window.openedLink = link; }, close() {}
      } };
    });
    const html = fs.readFileSync(path.join(__dirname, '../src/webapp/templates/form.html'), 'utf8');
    const endpoint = html.match(/fetch\('([^']+)'/)[1];
    await page.route('**/*', async route => {
      if (route.request().method() === 'POST') {
        requests.push({ url: new URL(route.request().url()).pathname, body: route.request().postDataJSON(), headers: route.request().headers() });
        return route.fulfill({ status: fail ? 500 : 200, contentType: 'application/json', body: JSON.stringify(fail ? {} : { link: 'https://t.me/+test' }) });
      }
      return route.fulfill({ contentType: route.request().url().endsWith('/') ? 'text/html' : 'text/javascript', body: route.request().url().endsWith('/') ? html : '' });
    });
    page.on('dialog', dialog => dialog.accept());
    await page.goto('https://example.test/');
    const button = page.locator('#nextBtn');
    assert(await button.isDisabled());
    await page.locator('#privacy').check();
    await page.locator('#rules').check();
    await page.locator('[name=fio]').evaluate(el => { el.value = 'Врач'; el.dispatchEvent(new Event('change', { bubbles: true })); });
    if (await page.locator('select').count()) {
      assert(await button.isDisabled());
      await page.locator('select').evaluate(el => { el.selectedIndex = 2; el.dispatchEvent(new Event('change', { bubbles: true })); });
    }
    assert.equal(await button.isDisabled(), false, 'change-only input must enable registration');
    await page.locator('#privacy').uncheck();
    assert(await button.isDisabled());
    await page.locator('#privacy').check();
    await page.locator('[name=fio]').fill('   ');
    assert(await button.isDisabled());
    await page.locator('[name=fio]').fill('Врач');
    assert.equal(await button.isDisabled(), false);
    await page.locator('[name=fio]').evaluate(el => { el.value = ''; window.dispatchEvent(new Event('focus')); });
    assert(await button.isDisabled());
    await page.locator('[name=fio]').evaluate(el => { el.value = 'Врач'; window.dispatchEvent(new Event('pageshow')); });
    assert.equal(await button.isDisabled(), false);
    await button.click();
    await page.waitForFunction(() => !document.getElementById('nextBtn').disabled);
    fail = false;
    await button.click();
    await page.waitForFunction(() => window.openedLink === 'https://t.me/+test');
    assert.equal(requests.length, 2);
    assert.equal(requests[1].url, endpoint);
    assert.equal(requests[1].body.fio, 'Врач');
    assert.equal(requests[1].headers['x-telegram-init-data'], 'signed-test-data');
    assert.deepEqual(errors, []);
    console.log('PASS: mobile change/input, consent, restore, error retry, authenticated submission ' + endpoint);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
