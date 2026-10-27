// Optional smoke check against an isolated Chrome instance with CDP on port 9223.
// Set EDITOR_USER and EDITOR_PASSWORD to an existing teacher account.
import {writeFile} from 'node:fs/promises';
const targets = await (await fetch('http://127.0.0.1:9223/json/list')).json();
const target = targets.find(t => t.type === 'page' && (t.url === 'about:blank' || t.url.startsWith('http://127.0.0.1:8000/')));
if (!target) throw new Error('Start a separate Chrome headless profile with a blank page first');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {ws.onopen = resolve; ws.onerror = reject;});
const waiting = new Map(); let id = 0;
const errors = [];
ws.onmessage = event => {
  const message = JSON.parse(event.data);
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
  const pending = waiting.get(message.id);
  if (pending) { waiting.delete(message.id); message.error ? pending.reject(message.error) : pending.resolve(message.result); }
};
const call = (method, params = {}) => new Promise((resolve, reject) => {
  const key = ++id; waiting.set(key, {resolve, reject}); ws.send(JSON.stringify({id:key, method, params}));
});
const evaluate = async expression => {
  const result = await call('Runtime.evaluate', {expression, awaitPromise:true, returnByValue:true});
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
const pause = () => new Promise(resolve => setTimeout(resolve, 300));
const until = async expression => {
  for (let n = 0; n < 80; n++) { if (await evaluate(expression)) return; await pause(); }
  throw new Error('Timed out: ' + expression);
};
try {
  await call('Runtime.enable'); await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride', {width:1440, height:1000, deviceScaleFactor:1, mobile:false});
  await call('Page.navigate', {url:'http://127.0.0.1:8000/comptes/connexion/'});
  await until('!!document.querySelector("input[name=csrfmiddlewaretoken]")');
  const user = process.env.EDITOR_USER, password = process.env.EDITOR_PASSWORD;
  if (!user || !password) throw new Error('Missing teacher credentials');
  await evaluate(`(async () => {
    const data = new URLSearchParams({username:${JSON.stringify(user)}, password:${JSON.stringify(password)}, csrfmiddlewaretoken:document.querySelector('input[name=csrfmiddlewaretoken]').value});
    await fetch('/comptes/connexion/', {method:'POST',body:data});
  })()`);
  await call('Page.navigate', {url:'http://127.0.0.1:8000/pedagogie/cours/ajouter/'});
  await until('!!window.hugerte && typeof hugerte.get === "function" && hugerte.get().length === 1 && hugerte.get()[0].initialized');
  const initial = await evaluate(`({language:hugerte.get()[0].options.get('language'), menu:document.querySelector('.tox-menubar')?.textContent, editors:hugerte.get().length})`);
  if (!initial.menu.includes('Fichier') || initial.language !== 'fr_FR') throw new Error(JSON.stringify(initial));
  await evaluate(`document.getElementById('add-chapter').click()`);
  await until('hugerte.get().length === 2 && hugerte.get()[1].initialized');
  await until('document.querySelector("[data-chapter] input[type=file]").dataset.pickerReady === "1"');
  const picked = await evaluate(`(() => {
    const input = document.querySelector('[data-chapter] input[type=file]');
    const choose = name => {
      const data = new DataTransfer(); data.items.add(new File(['preview'], name, {type:'application/pdf',lastModified:123}));
      input.files = data.files; input.dispatchEvent(new Event('change', {bubbles:true}));
    };
    choose('First.pdf'); choose('Second.pdf'); choose('Second.pdf');
    const accumulated = [...input.files].map(file => file.name);
    input.nextElementSibling.querySelector('li button').click();
    return {accumulated, remaining:[...input.files].map(file => file.name)};
  })()`);
  if (picked.accumulated.join(',') !== 'First.pdf,Second.pdf' || picked.remaining.join(',') !== 'Second.pdf') throw new Error(JSON.stringify(picked));
  const sync = await evaluate(`(() => {
    const editor = hugerte.get()[1];
    editor.setContent('<h2>Chapitre test</h2><p style="text-align:center"><strong>Gras</strong></p><table><tbody><tr><td>Cellule</td></tr></tbody></table>');
    hugerte.triggerSave();
    const row = document.querySelector('[data-chapter]');
    return {saved:row.querySelector('textarea').value, uploads:row.querySelector('input[type=file]').accept};
  })()`);
  if (!sync.saved.includes('<strong>Gras</strong>') || sync.uploads !== '.pdf,.docx') throw new Error(JSON.stringify(sync));
  if (process.env.EDITOR_SCREENSHOT) {
    const screenshot = await call('Page.captureScreenshot', {format:'png', captureBeyondViewport:false});
    await writeFile(process.env.EDITOR_SCREENSHOT, Buffer.from(screenshot.data, 'base64'));
  }
  await evaluate(`document.querySelector('[data-remove-chapter]').click()`);
  if (!(await evaluate(`hugerte.get().length === 1 && document.querySelector('[data-chapter]').hidden`))) throw new Error('Editor removal failed');
  if (process.env.EDITOR_READING_URL) {
    await call('Page.navigate', {url:process.env.EDITOR_READING_URL});
    await until('Number(document.getElementById("lecteur")?.dataset.readingPages) > 0');
    const check = await evaluate(`(() => {
      const reader = document.getElementById('lecteur');
      const total = Number(reader.dataset.readingPages);
      const source = document.getElementById('reading-source').content;
      const expected = source.textContent.replace(/\\s+/g, '');
      const texts = [], gaps = [];
      let images = 0, rows = 0, fits = true;
      for (let page = 1; page <= total; page++) {
        reader.querySelector('[data-reading-page="' + page + '"]')?.click();
        const body = reader.querySelector('.course-reader-body');
        const bounds = body.getBoundingClientRect();
        texts.push(body.textContent.replace(/\\s+/g, ''));
        images += body.querySelectorAll('img').length;
        rows += body.querySelectorAll('tr').length;
        gaps.push(Math.round(bounds.bottom - body.lastElementChild.getBoundingClientRect().bottom - parseFloat(getComputedStyle(body).paddingBottom)));
        body.querySelectorAll('img').forEach(img => {const rect = img.getBoundingClientRect(); fits = fits && rect.left >= bounds.left && rect.right <= bounds.right;});
      }
      reader.querySelector('[data-reading-page="2"]')?.click();
      return {pages:total, fits, gaps, contentPreserved:texts.join('') === expected,
        rowsPreserved:rows === source.querySelectorAll('tr').length, imagesPreserved:images === source.querySelectorAll('img').length,
        horizontalOverflow:document.documentElement.scrollWidth > innerWidth};
    })()`);
    if (!check.fits || check.horizontalOverflow || !check.contentPreserved || !check.rowsPreserved || !check.imagesPreserved || check.gaps.some(gap => gap > 30)) throw new Error(JSON.stringify(check));
    if (process.env.EDITOR_SCREENSHOT) {
      const screenshot = await call('Page.captureScreenshot', {format:'png',captureBeyondViewport:false});
      await writeFile(process.env.EDITOR_SCREENSHOT, Buffer.from(screenshot.data,'base64'));
    }
    console.log(JSON.stringify({reader:check}));
    await call('Emulation.setDeviceMetricsOverride', {width:390, height:844, deviceScaleFactor:1, mobile:true});
    await pause();
    if (await evaluate('document.documentElement.scrollWidth > innerWidth')) throw new Error('Mobile horizontal overflow');
  }
  if (errors.length) throw new Error(JSON.stringify(errors));
  console.log(JSON.stringify({frenchMenu:initial.menu, editorsAddedAndRemoved:true, formattingSynced:true, chapterUpload:true, cumulativeDocumentSelection:picked, browserErrors:errors.length}));
} finally { ws.close(); }
