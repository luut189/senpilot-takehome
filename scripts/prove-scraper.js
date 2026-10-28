// Investigation only: pass this function to playwright-cli run-code.
// The production implementation is Python; this uses the preinstalled browser
// tooling when PyPI installation is unavailable. Run in a fresh CLI session.
async (page) => {
  page.setDefaultTimeout(30000);
  await page.goto('https://uarb.novascotia.ca/fmi/webd/UARB15');
  await page.locator('.fm_object_254 .text').dblclick();
  const editor = page.locator('.fm_object_254 [contenteditable=true]');
  await editor.fill('M12205');
  await editor.press('Tab');
  await page.locator('.fm_object_286 .text').waitFor();
  const fields = {
    matter_number: '.fm_object_286 .text',
    title: '[id="b0p0o290i0i0r1"]',
    matter_type: '.fm_object_287 .text',
    status: '.fm_object_289 .text',
    date_received: '.fm_object_292 .text',
    decision_date: '.fm_object_294 .text',
    outcome: '.fm_object_295 .text',
    category: '.fm_object_298 .text',
  };
  const matter = {};
  for (const [key, selector] of Object.entries(fields)) {
    matter[key] = (await page.locator(selector).innerText()).trim() || null;
  }
  if (matter.matter_number !== 'M12205') throw Error('Wrong matter loaded');
  const counts = {};
  const categories = ['Exhibits', 'Key Documents', 'Other Documents', 'Transcripts', 'Recordings'];
  const labels = await page.getByRole('button').allInnerTexts();
  for (const category of categories) {
    const matches = labels.map(s => s.trim().match(new RegExp(`^${category} - ([0-9]+)$`))).filter(Boolean);
    if (matches.length !== 1) throw Error(`Invalid count: ${category}`);
    counts[category] = Number(matches[0][1]);
  }
  if (!counts['Other Documents']) throw Error('Category empty');
  await page.getByRole('button', {name: /^Other Documents -/}).click();
  const rows = page.getByRole('row').filter({has: page.getByRole('button', {name: 'GO GET IT', exact: true})});
  const row = rows.first();
  await row.waitFor();
  const document = {};
  for (const [key, id] of Object.entries({document_number: 201, title: 202, date: 203, security: 204, extension: 308})) {
    document[key] = (await row.locator(`.fm_object_${id} .text`).innerText()).trim();
  }
  const name = document.document_number + document.extension;
  if (!/^[0-9]+\.[A-Za-z0-9]+$/.test(name)) throw Error('Unsafe or unexpected filename');
  const dialog = page.getByRole('dialog');
  let attempts = 0;
  for (; attempts < 2; attempts++) {
    await row.getByRole('button', {name: 'GO GET IT', exact: true}).click();
    const button = dialog.getByRole('button', {name, exact: true});
    await button.waitFor();
    try {
      const [download] = await Promise.all([
        page.waitForEvent('download', {timeout: 60000}),
        (async () => {
          await button.click();
          await dialog.getByRole('button', {name: 'Close', exact: true}).click();
        })(),
      ]);
      await download.saveAs(`proof-downloads/repro-${name}`);
      const failure = await download.failure();
      if (failure) throw Error(failure);
      return {matter, counts, document, attempts: attempts + 1, path: `proof-downloads/repro-${name}`, failure};
    } catch (error) {
      if (attempts === 1 || error.name !== 'TimeoutError') throw error;
    } finally {
      if (await dialog.count()) await dialog.getByRole('button', {name: 'Close', exact: true}).click();
    }
  }
}
