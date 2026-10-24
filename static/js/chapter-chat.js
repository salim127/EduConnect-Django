(() => {
  const form = document.getElementById('chapter-chat-form');
  if (!form) return;
  const panel = document.getElementById('chapter-assistant');
  const log = document.getElementById('chapter-chat-messages');
  const question = document.getElementById('chapter-chat-question');
  const send = document.getElementById('chapter-chat-send');
  const reset = document.getElementById('chapter-chat-reset');
  const status = document.getElementById('chapter-chat-status');
  const error = document.getElementById('chapter-chat-error');
  let busy = false, loaded = false;
  const request = async (action, value = '') => {
    const response = await fetch(form.dataset.url, {method: 'POST', credentials: 'same-origin',
      body: new URLSearchParams({action, question: value, csrfmiddlewaretoken: form.querySelector('[name=csrfmiddlewaretoken]').value})});
    let data;
    try { data = await response.json(); } catch { throw new Error('La session ou le chapitre n’est plus accessible. Rechargez la page.'); }
    if (!response.ok) throw new Error(data.error || 'L’assistant est indisponible. Réessayez.');
    return data;
  };
  function append(turn) {
    log.querySelector('[data-chat-welcome]')?.remove();
    const entry = document.createElement('article'); entry.className = 'border-bottom pb-3 mb-3';
    const label = document.createElement('strong'); label.textContent = 'Vous';
    const asked = document.createElement('p'); asked.className = 'mt-1'; asked.textContent = turn.question;
    const bot = document.createElement('strong'); bot.textContent = 'Assistant';
    const answer = document.createElement('p'); answer.className = 'mt-1 mb-2'; answer.style.whiteSpace = 'pre-line'; answer.textContent = turn.answer;
    entry.append(label, asked, bot, answer);
    (turn.citations || []).forEach(citation => {
      const reference = document.createElement('details'); reference.className = 'small border rounded p-2 mt-2';
      const title = document.createElement('summary'); title.textContent = 'Passage utilisé : ' + citation.label;
      const quote = document.createElement('blockquote'); quote.className = 'mt-2 mb-1'; quote.textContent = citation.quote;
      reference.append(title, quote);
      if (citation.url && /^\/pedagogie\/supports\/\d+\/telecharger\/$/.test(citation.url)) {
        const link = document.createElement('a'); link.href = citation.url; link.textContent = 'Télécharger le document cité'; reference.append(link);
      }
      entry.append(reference);
    });
    if (turn.truncated) { const note = document.createElement('p'); note.className = 'small text-muted mt-2'; note.textContent = 'Le contenu étant long, une partie du chapitre et des documents a été examinée.'; entry.append(note); }
    log.append(entry); log.scrollTop = log.scrollHeight;
  }
  function lock(value) { busy = value; send.disabled = reset.disabled = value; status.textContent = value ? 'L’assistant prépare sa réponse…' : ''; }
  async function loadHistory() {
    if (loaded || busy) return;
    lock(true); error.textContent = '';
    try { const data = await request('history'); data.history.forEach(append); loaded = true; }
    catch (reason) { error.textContent = reason.message; }
    finally { lock(false); }
  }
  panel.addEventListener('toggle', () => { if (panel.open) loadHistory(); });
  document.querySelectorAll('[data-open-chapter-chat]').forEach(button => button.addEventListener('click', () => {
    panel.open = true;
    panel.scrollIntoView({block: 'start', behavior: 'smooth'});
    question.focus({preventScroll: true});
  }));
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (busy || !question.value.trim()) return;
    const value = question.value.trim(); lock(true); error.textContent = '';
    try { const data = await request('ask', value); append(data); question.value = ''; loaded = true; }
    catch (reason) { error.textContent = reason.message; }
    finally { lock(false); question.focus(); }
  });
  reset.addEventListener('click', async () => {
    if (busy) return;
    lock(true); error.textContent = '';
    try { await request('reset'); log.replaceChildren(); question.value = ''; loaded = true; }
    catch (reason) { error.textContent = reason.message; }
    finally { lock(false); }
  });
})();
