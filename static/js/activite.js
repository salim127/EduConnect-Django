(() => {
  const label = document.getElementById('temps-actif');
  if (!label) return;
  const token = document.querySelector('[name=csrfmiddlewaretoken]').value;
  let lastInteraction = Date.now(), sending = false, stopped = false, seconds = 0;
  const active = () => !stopped && !document.hidden && document.hasFocus() && Date.now() - lastInteraction < 60000;
  async function ping(forcePause = false) {
    if (sending) return;
    sending = true;
    const running = !forcePause && active();
    try {
      const result = await fetch(label.dataset.url, {method: 'POST', headers: {'X-CSRFToken': token, 'Content-Type': 'application/x-www-form-urlencoded'}, body: new URLSearchParams({active: String(running)}), keepalive: true});
      if (!result.ok) throw new Error('signal');
      const data = await result.json();
      seconds += data.secondes_ajoutees || 0;
      label.textContent = `${running ? 'Temps actif sur cette page' : 'Suivi en pause'} : ${Math.floor(seconds / 60)} min ${seconds % 60} s. Pause après 60 s d’inactivité ou lorsque la page n’est plus active.`;
    } catch { label.textContent = 'Suivi du temps indisponible. Votre réponse peut toujours être enregistrée.'; }
    finally { sending = false; }
  }
  ['pointerdown', 'keydown', 'scroll', 'input'].forEach(name => document.addEventListener(name, () => {lastInteraction = Date.now();}, {passive: true}));
  document.addEventListener('visibilitychange', () => ping());
  window.addEventListener('blur', () => ping(true));
  window.addEventListener('focus', () => {lastInteraction = Date.now(); ping();});
  window.addEventListener('pagehide', () => {stopped = true; ping(true);});
  document.querySelector('form.card-x').addEventListener('submit', () => {stopped = true; ping(true);});
  setInterval(() => ping(), 10000);
  ping();
})();
