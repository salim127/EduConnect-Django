// Browser interactions use synthetic help replies; no AI calls or exercise submissions.
const targets = await (await fetch('http://127.0.0.1:9223/json/list')).json();
const target = targets.find(t => t.type === 'page' && (t.url === 'about:blank' || t.url.startsWith('http://127.0.0.1:8000/')));
if (!target) throw new Error('An isolated Chrome test profile is required');
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
let identity = 0;
const pending = new Map(), errors = [];
socket.onmessage = event => {
  const value = JSON.parse(event.data);
  if (value.method === 'Runtime.exceptionThrown') errors.push(value.params.exceptionDetails.exception?.description || value.params.exceptionDetails.text);
  const callback = pending.get(value.id);
  if (callback) { pending.delete(value.id); value.error ? callback.reject(value.error) : callback.resolve(value.result); }
};
const call = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++identity; pending.set(id, {resolve, reject}); socket.send(JSON.stringify({id, method, params}));
});
const evaluate = async expression => {
  const result = await call('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
const until = async expression => {
  for (let n = 0; n < 100; n++) {
    if (await evaluate(expression)) return;
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  throw new Error('Timed out: ' + expression);
};
const navigate = async (url, selector) => {
  await call('Page.navigate', {url});
  await until(`!!document.querySelector(${JSON.stringify(selector)}) && document.readyState === 'complete'`);
};
try {
  if (!process.env.EDITOR_USER || !process.env.EDITOR_PASSWORD || !process.env.AI_CHAPTER_URL) throw new Error('Missing account or chapter URL');
  await call('Runtime.enable'); await call('Network.enable'); await call('Network.setCacheDisabled', {cacheDisabled: true});
  await navigate('http://127.0.0.1:8000/comptes/connexion/', '[name=csrfmiddlewaretoken]');
  await evaluate(`(async () => { await fetch('/comptes/connexion/', {method:'POST', body:new URLSearchParams({username:${JSON.stringify(process.env.EDITOR_USER)},password:${JSON.stringify(process.env.EDITOR_PASSWORD)},csrfmiddlewaretoken:document.querySelector('[name=csrfmiddlewaretoken]').value})}); })()`);
  await navigate(process.env.AI_CHAPTER_URL, '[data-open-chapter-chat]');
  const links = await evaluate(`({study:document.querySelector('a[href$="/revision/"]').href,practice:document.querySelector('a[href$="/entrainement/"]').href})`);
  await navigate(links.study, 'form[data-ai-wait]');
  const study = await evaluate(`({actions:[...document.querySelectorAll('input[name=action]')].map(n=>n.value),overflow:document.documentElement.scrollWidth > innerWidth+1})`);
  if (!study.actions.includes('summary') || !study.actions.includes('cards') || study.overflow) throw new Error(JSON.stringify(study));
  await navigate(links.practice, 'form[data-ai-wait]');
  if (!await evaluate(`document.body.textContent.includes('Cet entraînement reste personnel.')`)) throw new Error('Missing personal practice text');
  await navigate('http://127.0.0.1:8000/pedagogie/exercices/', 'a[href^="/pedagogie/exercices/"]');
  const exercise = await evaluate(`[...document.querySelectorAll('a')].find(a=>/^\\/pedagogie\\/exercices\\/\\d+\\/$/.test(a.pathname)).href`);
  await navigate(exercise, '#exercise-answer-form');
  await evaluate(`(async () => {
    const original = window.fetch;
    // Clone the form to initialize a synthetic correction control with the production JS.
    const previous = document.getElementById('exercise-answer-form'), form = previous.cloneNode(true); previous.replaceWith(form);
    const field = form.querySelector('[data-exercise-question]');
    const button = document.createElement('button'); button.type='button'; button.dataset.exerciseHelp='correct'; button.textContent='Correction de test'; field.append(button);
    if (!field.querySelector('[data-open-correction]')) { const panel=document.createElement('div');panel.dataset.openCorrection='';field.append(panel); }
    window.fetch = async (url, options) => {
      if (String(url).endsWith('/aide/')) {
        const action=options.body.get('action');
        return new Response(JSON.stringify({correction:{score:1,maximum:2,criteres:[{critere:'Définition',points:1,maximum:2,commentaire:'À préciser'}],corrects:['Structure comprise'],manquants:['Un exemple'],conseil:'Ajoutez un exemple.',truncated:false}}),{headers:{'Content-Type':'application/json'}});
      }
      return original(url,options);
    };
    (0,eval)(await (await original('/static/js/exercise-help.js')).text());
  })()`);
  await evaluate(`document.querySelector('[data-exercise-help="correct"]').click()`);
  await until(`document.querySelector('[data-open-correction]').textContent.includes('Ajoutez un exemple.')`);
  await navigate('http://127.0.0.1:8000/pedagogie/exercices/ajouter/', '#id_bareme');
  await evaluate(`(() => { const type=document.getElementById('id_type_exercice');type.value='ouverte';type.dispatchEvent(new Event('change'));document.getElementById('add-question').click(); })()`);
  const rubric = await evaluate(`({firstVisible:!document.getElementById('id_bareme').closest('.field').hidden,extraVisible:!document.querySelector('[name="questions-0-bareme"]').closest('.field').hidden})`);
  if (!rubric.firstVisible || !rubric.extraVisible) throw new Error(JSON.stringify(rubric));
  if (errors.length) throw new Error(JSON.stringify(errors));
  console.log(JSON.stringify({study,personalPractice:true,correctionDisplayed:true,rubric,browserErrors:0}));
} finally { socket.close(); }
