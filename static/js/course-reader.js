// Paginate by the actual rendered height, including responsive text, tables and images.
(() => {
  const reader = document.getElementById('lecteur');
  const source = document.getElementById('reading-source');
  const body = reader?.querySelector('.course-reader-body');
  if (!body || !source?.content.children.length) return;
  const originals = [];
  for (const element of source.content.children) {
    const node = element.cloneNode(true);
    const previous = originals.at(-1);
    if (node.matches('.reading-table') && previous?.matches('.reading-table')) {
      previous.querySelector('tbody').append(...node.querySelectorAll('tr'));
    } else originals.push(node);
  }
  const top = document.createElement('div');
  const bottom = document.createElement('div');
  let pages = [], started = false, lastWidth = 0, lastHeight = 0, timer;
  const selectedPage = () => Math.max(1, Number(new URL(location.href).searchParams.get('page')) || 1);
  const clone = node => node.cloneNode(true);

  function show(number, scroll = false) {
    const index = Math.max(0, Math.min(pages.length - 1, number - 1));
    body.replaceChildren(...pages[index].map(clone));
    reader.querySelector('.reading-status strong').textContent = `Page ${index + 1} / ${pages.length}`;
    reader.dataset.readingPages = pages.length;
    const url = new URL(location.href);
    url.searchParams.set('page', index + 1);
    if (scroll) history.pushState(null, '', url);
    else history.replaceState(null, '', url);
    for (const host of [top, bottom]) {
      host.replaceChildren();
      if (pages.length === 1) continue;
      const nav = document.createElement('nav');
      nav.className = 'reading-pagination';
      nav.setAttribute('aria-label', 'Pages du chapitre');
      const link = (label, page, className) => {
        const a = document.createElement('a');
        const target = new URL(location.href);
        target.searchParams.set('page', page); target.hash = 'lecteur';
        a.href = target.href; a.textContent = label; a.className = className;
        a.dataset.readingPage = page;
        a.addEventListener('click', event => {
          if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
          event.preventDefault(); show(page, true);
        });
        return a;
      };
      nav.append(index > 0 ? link('← Page précédente', index, 'btn btn-soft btn-sm') : document.createElement('span'));
      const numbers = document.createElement('div');
      numbers.className = 'd-flex align-items-center flex-wrap gap-1 justify-content-center';
      let skipped = false;
      for (let n = 1; n <= pages.length; n++) {
        if (n !== 1 && n !== pages.length && Math.abs(n - index - 1) > 2) {
          if (!skipped) { const dots = document.createElement('span'); dots.textContent = '…'; numbers.append(dots); }
          skipped = true; continue;
        }
        skipped = false;
        const a = link(String(n), n, 'reading-page-number' + (n === index + 1 ? ' is-active' : ''));
        if (n === index + 1) a.setAttribute('aria-current', 'page');
        numbers.append(a);
      }
      nav.append(numbers);
      nav.append(index + 1 < pages.length ? link('Page suivante →', index + 2, 'btn btn-primary btn-sm') : document.createElement('span'));
      host.append(nav);
    }
    if (scroll) reader.scrollIntoView({block: 'start'});
  }

  function paginate() {
    const width = body.getBoundingClientRect().width;
    if (!width) return;
    const budget = Math.max(560, Math.min(1000, innerHeight - 40));
    const measure = document.createElement('div');
    measure.className = 'course-reader-body course-rich reading-measure';
    measure.style.width = width + 'px';
    measure.setAttribute('aria-hidden', 'true');
    reader.append(measure);
    const result = [];
    const fits = () => measure.getBoundingClientRect().height <= budget;
    const finish = () => {
      if (measure.children.length) result.push([...measure.children].map(clone));
      measure.replaceChildren();
    };
    const breakPage = () => {
      const heading = measure.lastElementChild?.matches('.reading-heading') && measure.children.length > 1 ? measure.lastElementChild : null;
      heading?.remove(); finish(); if (heading) measure.append(heading);
    };
    for (const original of originals) {
      const node = clone(original);
      node.querySelectorAll('img').forEach(img => { img.loading = 'eager'; });
      measure.append(node);
      if (fits() || measure.children.length === 1 && !node.matches('.reading-table')) continue;
      node.remove();
      if (node.matches('.reading-table')) {
        // Fit as many complete table rows as possible instead of moving a whole table.
        const rows = [...node.querySelectorAll('tr')];
        let wrapper, table;
        const startTable = () => {
          wrapper = document.createElement('div'); wrapper.className = 'reading-table';
          table = document.createElement('table');
          const tbody = document.createElement('tbody'); table.append(tbody); wrapper.append(table); measure.append(wrapper);
          return tbody;
        };
        let tbody = startTable();
        for (const row of rows) {
          tbody.append(row);
          if (fits()) continue;
          row.remove();
          if (!tbody.children.length) wrapper.remove();
          if (measure.children.length) breakPage();
          tbody = startTable(); tbody.append(row);
          // A single very tall row is allowed to grow; its contents are never clipped.
        }
      } else {
        if (node.matches('.reading-image') && measure.children.length) {
          const remaining = budget - measure.getBoundingClientRect().height - 30;
          if (remaining >= 170) {
            node.querySelector('img').style.setProperty('max-height', Math.floor(remaining) + 'px', 'important');
            measure.append(node);
            if (fits()) continue;
            node.remove();
          }
        }
        if (measure.children.length) breakPage();
        measure.append(node);
      }
    }
    finish(); measure.remove();
    pages = result.length ? result : [[]];
    if (!started) {
      reader.querySelectorAll('.reading-pagination').forEach(nav => nav.remove());
      body.before(top); body.after(bottom); started = true;
    }
    lastWidth = width; lastHeight = innerHeight;
    show(selectedPage());
  }

  async function start() {
    // Preload image dimensions before measuring so a late image doesn't invalidate page breaks.
    const images = originals.flatMap(node => [...node.querySelectorAll('img')]);
    await Promise.race([
      Promise.all(images.map(img => new Promise(resolve => {
        const image = new Image();
        image.onload = () => { resolve(); if (started) schedule(); };
        image.onerror = resolve;
        image.src = img.src;
        if (image.complete) resolve();
      }))),
      new Promise(resolve => setTimeout(resolve, 4000))
    ]);
    if (document.fonts?.ready) await document.fonts.ready;
    paginate();
    new ResizeObserver(() => {
      if (Math.abs(body.getBoundingClientRect().width - lastWidth) > 1 || innerHeight !== lastHeight) schedule();
    }).observe(body);
    window.addEventListener('resize', schedule);
    window.addEventListener('popstate', () => show(selectedPage()));
  }
  function schedule() { clearTimeout(timer); timer = setTimeout(paginate, 150); }
  start();
})();
