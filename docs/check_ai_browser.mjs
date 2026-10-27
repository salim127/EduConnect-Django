// UI check with a synthetic chat response; no live AI request and no exercise creation.
const targets = await (await fetch('http://127.0.0.1:9223/json/list')).json();
const target = targets.find(t => t.type === 'page' && (t.url === 'about:blank' || t.url.startsWith('http://127.0.0.1:8000/')));
if (!target) throw new Error('An isolated test Chrome profile is required');
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
let id = 0;
const waiting = new Map(), errors = [];
socket.onmessage = event => {
  const message = JSON.parse(event.data);
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
  const item = waiting.get(message.id);
  if (item) { waiting.delete(message.id); message.error ? item.reject(message.error) : item.resolve(message.result); }
};
const call = (method, params = {}) => new Promise((resolve, reject) => {
  const key = ++id; waiting.set(key, {resolve, reject}); socket.send(JSON.stringify({id:key, method, params}));
});
const evaluate = async expression => {
  const result = await call('Runtime.evaluate', {expression, awaitPromise:true, returnByValue:true});
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
const until = async expression => {
  for (let n = 0; n < 70; n++) {
    if (await evaluate(expression)) return;
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error('Timed out: ' + expression);
};
try {
  await call('Runtime.enable');
  await call('Network.enable');
  await call('Network.setCacheDisabled', {cacheDisabled:true});
  await call('Page.navigate', {url:'http://127.0.0.1:8000/comptes/connexion/'});
  await until('!!document.querySelector("[name=csrfmiddlewaretoken]")');
  if (!process.env.EDITOR_USER || !process.env.EDITOR_PASSWORD || !process.env.AI_CHAPTER_URL) throw new Error('Missing test account or chapter URL');
  await evaluate(`(async () => {
    const data = new URLSearchParams({username:${JSON.stringify(process.env.EDITOR_USER)},password:${JSON.stringify(process.env.EDITOR_PASSWORD)},csrfmiddlewaretoken:document.querySelector('[name=csrfmiddlewaretoken]').value});
    await fetch('/comptes/connexion/',{method:'POST',body:data});
  })()`);
  await call('Page.navigate', {url:process.env.AI_CHAPTER_URL});
  await until('!!document.querySelector("[data-open-chapter-chat]")');
  await until('document.readyState === "complete"');
  const generate = await evaluate(`document.querySelector('a[href$="/generer-exercices/"]').href`);
  await evaluate(`document.querySelector('[data-open-chapter-chat]').click()`);
  await until('document.getElementById("chapter-assistant").open && !document.getElementById("chapter-chat-send").disabled');
  await evaluate(`(() => {
    const original = window.fetch;
    window.fetch = async (url, options) => {
      if (String(url).endsWith('/assistant/') && options?.body?.get('action') === 'ask') {
        return new Response(JSON.stringify({question:options.body.get('question'),answer:'HTML structure la page, CSS définit sa présentation. <img src=x onerror=alert(1)>',citations:[{label:'Chapitre de test',quote:'HTML structure la page.',url:''}],truncated:false}),{headers:{'Content-Type':'application/json'}});
      }
      return original(url, options);
    };
    document.getElementById('chapter-chat-question').value = 'Quelle différence entre HTML et CSS ?';
    document.getElementById('chapter-chat-form').requestSubmit();
  })()`);
  await until('!document.getElementById("chapter-chat-send").disabled && document.querySelectorAll("#chapter-chat-messages article").length === 1');
  const chat = await evaluate(`({citation:document.getElementById('chapter-chat-messages').textContent.includes('Passage utilisé'),safe:!document.querySelector('#chapter-chat-messages img'),error:document.getElementById('chapter-chat-error').textContent})`);
  if (!chat.citation || !chat.safe || chat.error) throw new Error(JSON.stringify(chat));
  await call('Page.navigate', {url:generate});
  await until('!!document.getElementById("generate-ai-form")');
  await until('document.readyState === "complete"');
  const generation = await evaluate(`({count:document.querySelector('[name=nombre]').value,type:document.querySelector('[name=type_exercice]').value,difficulty:document.querySelector('[name=difficulte]').value,button:document.getElementById('generate-ai-button').textContent.trim()})`);
  if (generation.count !== '5' || generation.type !== 'qcm' || generation.difficulty !== 'moyen') throw new Error(JSON.stringify(generation));
  if (errors.length) throw new Error(JSON.stringify(errors));
  console.log(JSON.stringify({chat, generation, browserErrors:0}));
} finally { socket.close(); }
