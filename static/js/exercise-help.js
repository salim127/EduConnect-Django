(() => {
  const form = document.getElementById('exercise-answer-form');
  if (!form) return;
  form.addEventListener('submit', () => {
    form.querySelectorAll('button:not([type="button"])').forEach(button => { button.disabled = true; });
  });
  const node = (tag, text, className = '') => {
    const element = document.createElement(tag); element.textContent = text; element.className = className; return element;
  };
  let busy = false;
  function feedback(container, value) {
    container.replaceChildren();
    const card = node('div', '', 'border rounded p-3');
    card.append(node('h6', `Correction proposée : ${value.score} / ${value.maximum}`), node('p', 'Évaluation indicative à confirmer par le professeur.', 'small text-muted'));
    const wrapper = node('div', '', 'table-responsive'), table = node('table', '', 'table table-sm');
    const head = document.createElement('thead'), heading = document.createElement('tr');
    ['Critère', 'Points', 'Commentaire'].forEach(text => heading.append(node('th', text))); head.append(heading); table.append(head);
    const body = document.createElement('tbody');
    value.criteres.forEach(item => { const row = document.createElement('tr'); row.append(node('td', item.critere), node('td', `${item.points} / ${item.maximum}`), node('td', item.commentaire)); body.append(row); });
    table.append(body); wrapper.append(table); card.append(wrapper);
    [['Points corrects', value.corrects], ['Points à compléter', value.manquants]].forEach(([title, items]) => {
      if (!items.length) return;
      const list = document.createElement('ul'); items.forEach(item => list.append(node('li', item))); card.append(node('strong', title), list);
    });
    card.append(node('p', 'Conseil : ' + value.conseil, 'mb-0'));
    if (value.truncated) card.append(node('p', 'Une partie des documents a été examinée, car le contenu est long.', 'small text-muted mt-2 mb-0'));
    container.append(card);
  }
  form.querySelectorAll('[data-exercise-help]').forEach(button => button.addEventListener('click', async () => {
    if (busy) return;
    const field = button.closest('[data-exercise-question]');
    const status = field.querySelector('[data-help-status]'), error = field.querySelector('[data-help-error]');
    const action = button.dataset.exerciseHelp;
    busy = true; error.textContent = ''; status.textContent = 'Préparation de l’aide…';
    form.querySelectorAll('[data-exercise-help]').forEach(item => { item.disabled = true; });
    try {
      const response = await fetch(form.dataset.helpUrl, {method: 'POST', credentials: 'same-origin', body: new URLSearchParams({
        action, index: field.dataset.exerciseQuestion, revision: form.dataset.revision, attempt: form.dataset.attempt,
        csrfmiddlewaretoken: form.querySelector('[name=csrfmiddlewaretoken]').value
      })});
      let data;
      try { data = await response.json(); } catch { throw new Error('La session ou l’exercice n’est plus accessible. Rechargez la page.'); }
      if (!response.ok) throw new Error(data.error || 'L’aide est indisponible. Réessayez.');
      feedback(field.querySelector('[data-open-correction]'), data.correction); button.textContent = 'Afficher ma correction IA';
    } catch (reason) { error.textContent = reason.message; }
    finally {
      busy = false; status.textContent = '';
      form.querySelectorAll('[data-exercise-help]').forEach(item => { item.disabled = false; });
    }
  }));
})();
