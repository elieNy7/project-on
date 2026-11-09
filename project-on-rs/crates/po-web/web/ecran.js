// Project-On — client d'un écran Web.
//
// Il ne contient aucune logique de mise en page : il dessine, en SVG, la liste d'affichage que
// Project-On a calculée pour la taille de cet écran (lignes déjà coupées et placées au pixel près).
// Il n'envoie que sa taille, ses accusés de réception et ses réponses au ping : rien qui pilote.
(() => {
  'use strict';
  const SVG = 'http://www.w3.org/2000/svg';
  const screenName = decodeURIComponent(location.pathname.split('/').filter(Boolean).pop() || 'salle');
  const stage = document.getElementById('stage');
  let ws = null;
  let retryDelay = 500;
  let current = null;
  let token = 0;
  const loadedFonts = new Set();

  function send(message) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message));
  }

  function announceSize() {
    send({ type: 'hello', width: window.innerWidth, height: window.innerHeight });
  }

  function rgba(c) {
    return `rgba(${c[0]},${c[1]},${c[2]},${(c[3] / 255).toFixed(3)})`;
  }

  // Les polices sont chargées AVANT de dessiner : jamais de texte dans une police de secours.
  async function ensureFonts(list) {
    const wanted = new Set();
    for (const item of list.items) {
      if (item.kind === 'text') wanted.add(`${item.weight} 64px "${item.family}"`);
    }
    await Promise.all([...wanted].filter((f) => !loadedFonts.has(f)).map((f) =>
      document.fonts.load(f).then(() => loadedFonts.add(f)).catch(() => {})));
  }

  function build(list) {
    const svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('viewBox', `0 0 ${list.width} ${list.height}`);
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.classList.add('layer');
    const background = document.createElementNS(SVG, 'rect');
    background.setAttribute('width', list.width);
    background.setAttribute('height', list.height);
    background.setAttribute('fill', rgba(list.background));
    svg.appendChild(background);
    for (const item of list.items) {
      if (item.kind === 'rect') {
        const rect = document.createElementNS(SVG, 'rect');
        for (const [k, v] of [['x', item.x], ['y', item.y], ['width', item.w], ['height', item.h], ['rx', item.radius]]) {
          rect.setAttribute(k, v);
        }
        rect.setAttribute('fill', rgba(item.color));
        svg.appendChild(rect);
      } else if (item.kind === 'text') {
        const text = document.createElementNS(SVG, 'text');
        text.setAttribute('x', item.x);
        text.setAttribute('y', item.baseline);
        text.setAttribute('text-anchor', item.anchor === 'middle' ? 'middle' : item.anchor === 'end' ? 'end' : 'start');
        text.setAttribute('font-family', `"${item.family}"`);
        text.setAttribute('font-weight', item.weight);
        text.setAttribute('font-size', item.size);
        text.setAttribute('fill', rgba(item.color));
        text.setAttribute('xml:space', 'preserve');
        text.style.fontKerning = 'normal';
        text.textContent = item.text;
        svg.appendChild(text);
      }
    }
    return svg;
  }

  async function show(message) {
    const mine = ++token;
    await ensureFonts(message.list);
    if (mine !== token) return; // une image plus récente est arrivée pendant le chargement
    const svg = build(message.list);
    stage.appendChild(svg);
    requestAnimationFrame(() => {
      svg.classList.add('visible');
      send({ type: 'ack', seq: message.seq });
    });
    const previous = current;
    current = svg;
    if (previous) {
      previous.classList.remove('visible');
      setTimeout(() => previous.remove(), 400);
    }
  }

  function connect() {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${scheme}://${location.host}/ws/${encodeURIComponent(screenName)}${location.search}`);
    ws.onopen = () => {
      retryDelay = 500;
      document.body.classList.remove('offline');
      announceSize();
    };
    ws.onmessage = (event) => {
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (message.type === 'frame') show(message);
      else if (message.type === 'ping') send({ type: 'pong' });
    };
    ws.onclose = () => {
      document.body.classList.add('offline');
      setTimeout(connect, retryDelay);
      retryDelay = Math.min(retryDelay * 2, 5000);
    };
    ws.onerror = () => ws.close();
  }

  let resizeTimer = 0;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(announceSize, 150);
  });
  connect();
})();
