document.querySelectorAll('form[data-ai-wait]').forEach(form => {
  form.addEventListener('submit', () => {
    document.querySelectorAll('form[data-ai-wait] button').forEach(button => { button.disabled = true; });
    document.querySelectorAll('[data-ai-status]').forEach(status => { status.textContent = 'Préparation en cours… Cela peut prendre quelques secondes.'; });
  });
});
