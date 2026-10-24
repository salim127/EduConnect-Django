// Accumulate selections in the original file field so Django receives all files.
(() => {
  if (typeof DataTransfer === 'undefined') return;
  const initialize = root => root.querySelectorAll('input[type="file"][multiple]').forEach(input => {
    if (input.dataset.pickerReady) return;
    input.dataset.pickerReady = '1';
    let selected = [...input.files];
    const container = document.createElement('div');
    container.className = 'border rounded p-3';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-soft';
    button.textContent = '+ Ajouter un ou plusieurs documents';
    const status = document.createElement('p');
    status.className = 'small text-muted mt-2 mb-0';
    status.setAttribute('role', 'status');
    const hint = document.createElement('p');
    hint.className = 'small text-muted mt-1 mb-0';
    hint.textContent = 'Ajoutez vos fichiers en une ou plusieurs sélections, puis enregistrez le cours.';
    const error = document.createElement('p');
    error.className = 'small text-danger mt-2 mb-0';
    error.setAttribute('role', 'alert');
    const list = document.createElement('ul');
    list.className = 'list-unstyled mt-3 mb-0';
    container.append(button, status, hint, error, list);
    input.after(container);
    input.classList.add('visually-hidden');
    const writeFiles = () => {
      const transfer = new DataTransfer();
      selected.forEach(file => transfer.items.add(file));
      input.files = transfer.files;
    };
    const render = () => {
      writeFiles();
      status.textContent = selected.length ? selected.length + ' document' + (selected.length > 1 ? 's' : '') + ' à ajouter' : 'Aucun nouveau document sélectionné';
      list.replaceChildren();
      selected.forEach((file, index) => {
        const row = document.createElement('li');
        row.className = 'd-flex gap-2 align-items-center border-top py-2';
        const label = document.createElement('span');
        label.className = 'flex-fill small text-break';
        label.textContent = file.name + ' · ' + (file.size / 1024 / 1024).toFixed(2) + ' Mo';
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'btn btn-sm btn-outline-danger';
        remove.textContent = 'Retirer';
        remove.setAttribute('aria-label', 'Retirer ' + file.name);
        remove.addEventListener('click', () => { selected.splice(index, 1); error.textContent = ''; render(); });
        row.append(label, remove);
        list.append(row);
      });
    };
    button.addEventListener('click', () => input.click());
    input.addEventListener('change', () => {
      error.textContent = '';
      const formats = input.accept.split(',').map(value => value.trim().toLowerCase()).filter(Boolean);
      const additions = [];
      for (const file of input.files) {
        if (formats.length && !formats.some(extension => file.name.toLowerCase().endsWith(extension))) {
          error.textContent = 'Formats acceptés : ' + input.accept; continue;
        }
        if (file.size > 15 * 1024 * 1024) { error.textContent = 'Chaque document doit faire au maximum 15 Mo.'; continue; }
        if (![...selected, ...additions].some(item => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified)) additions.push(file);
      }
      if (selected.length + additions.length > 10) error.textContent = 'Ajoutez au maximum 10 documents dans cette liste.';
      else if ([...selected, ...additions].reduce((sum, file) => sum + file.size, 0) > 50 * 1024 * 1024) error.textContent = 'Les documents ne doivent pas dépasser 50 Mo au total.';
      else selected.push(...additions);
      render();
    });
    render();
  });
  initialize(document);
  const chapters = document.getElementById('chapter-rows');
  if (chapters) new MutationObserver(() => initialize(chapters)).observe(chapters, {childList: true});
})();
