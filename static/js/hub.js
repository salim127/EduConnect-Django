// Interactions purement visuelles (aucune donnée n'est modifiée ici).
(function () {
  const body = document.body;
  const safe = (fn) => { try { return fn(); } catch (e) { return null; } };

  // Sidebar : repliable (ordinateur) / tiroir (mobile)
  if (safe(() => localStorage.getItem('sidebar') === 'collapsed')) body.classList.add('sidebar-collapsed');
  document.querySelectorAll('[data-sidebar-toggle]').forEach((b) => b.addEventListener('click', () => {
    if (window.innerWidth < 1200) return body.classList.toggle('sidebar-open');
    const c = body.classList.toggle('sidebar-collapsed');
    safe(() => localStorage.setItem('sidebar', c ? 'collapsed' : 'open'));
  }));
  document.querySelectorAll('.sidebar-backdrop').forEach((b) => b.addEventListener('click', () => body.classList.remove('sidebar-open')));

  // Modale de suppression partagée
  const modal = document.getElementById('deleteModal');
  if (modal) modal.addEventListener('show.bs.modal', (e) => {
    const t = e.relatedTarget;
    modal.querySelector('form').action = t.dataset.url;
    modal.querySelector('[data-name]').textContent = t.dataset.name;
  });

  // Formulaire d'exercice : afficher les propositions selon le type
  const type = document.getElementById('id_type_exercice');
  if (type) {
    const props = document.getElementById('id_propositions').closest('.field');
    const hint = document.getElementById('answer-hint');
    const area = document.getElementById('id_bonne_reponse');
    const propsArea = document.getElementById('id_propositions');
    const sel = document.createElement('select');
    sel.className = 'form-select';
    area.after(sel);
    sel.addEventListener('change', () => { area.value = sel.value; });
    const fill = (choices) => {
      const current = area.value.trim().toLowerCase();
      sel.innerHTML = '<option value="">--- Choisir la bonne réponse ---</option>';
      choices.forEach((c) => {
        const o = new Option(c, c);
        o.selected = c.toLowerCase() === current;
        sel.add(o);
      });
      area.value = sel.value;
    };
    const sync = () => {
      const t = type.value;
      props.style.display = t === 'qcm' ? '' : 'none';
      hint.textContent = { qcm: 'Choisissez la bonne réponse parmi les propositions.', vf: 'Choisissez Vrai ou Faux.', ouverte: 'Réponse attendue (modèle de correction).' }[t];
      area.style.display = t === 'ouverte' ? '' : 'none';
      sel.style.display = t === 'ouverte' ? 'none' : '';
      if (t === 'vf') fill(['Vrai', 'Faux']);
      if (t === 'qcm') fill(propsArea.value.split('\n').map((p) => p.trim()).filter(Boolean));
    };
    type.addEventListener('change', sync);
    propsArea.addEventListener('input', sync);
    sync();
  }

  // Filtres de démonstration (onglets + recherche visuelle)
  const cards = [...document.querySelectorAll('[data-kind]')];
  let kind = 'all'; let term = '';
  const apply = () => cards.forEach((c) => {
    const ok = (kind === 'all' || c.dataset.kind === kind) && c.textContent.toLowerCase().includes(term);
    c.classList.toggle('d-none', !ok);
  });
  document.querySelectorAll('[data-filter]').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('[data-filter]').forEach((x) => x.classList.remove('active'));
    b.classList.add('active'); kind = b.dataset.filter; apply();
  }));
  const s = document.querySelector('[data-demo-search]');
  if (s) s.addEventListener('input', () => { term = s.value.toLowerCase(); apply(); });
})();
