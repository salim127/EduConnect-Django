(() => {
  const base = new URL('../vendor/hugerte/', document.currentScript.src).href;
  const form = document.querySelector('textarea[data-rich-editor]')?.form;
  if (!form) return;
  const init = root => {
    root.querySelectorAll('textarea[data-rich-editor]').forEach(textarea => {
      if (textarea.dataset.editorReady || textarea.closest('[data-chapter]')?.hidden) return;
      if (!window.hugerte) { textarea.hidden = false; return; }
      textarea.dataset.editorReady = '1';
      if (!/<\/?(?:p|div|br|strong|b|em|i|u|h[1-6]|ul|ol|li|span|font|table)\b/i.test(textarea.value)) {
        textarea.value = textarea.value.replace(/\r?\n/g, '<br>');
      }
      hugerte.init({
        target: textarea,
        base_url: base.replace(/\/$/, ''), suffix: '.min',
        language: 'fr_FR', language_url: base + 'langs/fr_FR.js',
        height: 440, min_height: 300,
        menubar: 'file edit view insert format tools table',
        plugins: 'advlist autolink lists link image charmap preview anchor searchreplace visualblocks code fullscreen insertdatetime table wordcount directionality',
        toolbar: [
          'undo redo | blocks fontfamily fontsize | bold italic underline strikethrough | forecolor backcolor removeformat',
          'alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | lineheight | link image table | charmap insertdatetime | searchreplace preview fullscreen code'
        ],
        toolbar_mode: 'sliding', branding: false, promotion: false,
        browser_spellcheck: true, convert_urls: false, image_advtab: true,
        paste_data_images: false,
        content_style: 'body{font-family:Arial,sans-serif;font-size:16px;line-height:1.7;color:#25204a}table{border-collapse:collapse;max-width:100%}td,th{border:1px solid #dcd8ed;padding:8px}img{max-width:100%;height:auto}',
        setup(editor) {
          editor.on('change input undo redo', () => editor.save());
          editor.on('init', () => editor.save());
        }
      }).catch(() => { textarea.dataset.editorReady = ''; textarea.hidden = false; });
    });
  };
  form.addEventListener('submit', () => window.hugerte?.triggerSave());
  const rows = document.getElementById('chapter-rows');
  rows?.querySelectorAll('[data-chapter]').forEach(row => {
    if (row.querySelector('[name$="-DELETE"]').checked) row.hidden = true;
  });
  init(document);
  const add = document.getElementById('add-chapter');
  if (!add || !rows) return;
  add.addEventListener('click', () => {
    const total = document.getElementById('id_chapitres-TOTAL_FORMS');
    if (+total.value >= 100) return;
    const html = document.getElementById('chapter-template').innerHTML.replaceAll('__prefix__', total.value);
    rows.insertAdjacentHTML('beforeend', html);
    total.value = +total.value + 1;
    init(rows);
    rows.lastElementChild.querySelector('input:not([type="hidden"])').focus();
  });
  rows.addEventListener('click', event => {
    if (!event.target.matches('[data-remove-chapter]')) return;
    const row = event.target.closest('[data-chapter]');
    row.querySelector('[name$="-DELETE"]').checked = true;
    row.querySelectorAll('textarea[data-rich-editor]').forEach(area => window.hugerte?.get(area.id)?.remove());
    row.hidden = true;
  });
})();
