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

  function allItems(list) {
    const out = [];
    const walk = (items) => {
      for (const item of items || []) {
        out.push(item);
        if (item.kind === 'group') walk(item.items);
      }
    };
    walk(list.backdrop);
    walk(list.items);
    walk(list.overlay);
    return out;
  }

  // Les polices sont chargées AVANT de dessiner : jamais de texte dans une police de secours.
  async function ensureFonts(list) {
    const wanted = new Set();
    for (const item of allItems(list)) {
      if (item.kind === 'text') wanted.add(`${item.weight} 64px "${item.family}"`);
    }
    await Promise.all([...wanted].filter((f) => !loadedFonts.has(f)).map((f) =>
      document.fonts.load(f).then(() => loadedFonts.add(f)).catch(() => {})));
  }

  function el(name, attrs) {
    const node = document.createElementNS(SVG, name);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
    return node;
  }

  // Les dessins de la liste d'affichage : les mêmes que ceux de po-render (fenêtre, NDI, HDMI).
  function draw(parent, items, defs, ids) {
    for (const item of items || []) {
      if (item.kind === 'rect') {
        parent.appendChild(el('rect', { x: item.x, y: item.y, width: item.w, height: item.h, rx: item.radius, fill: rgba(item.color) }));
      } else if (item.kind === 'linear_gradient' || item.kind === 'radial_gradient') {
        const id = `g${ids.n++}`;
        const linear = item.kind === 'linear_gradient';
        const gradient = linear
          ? el('linearGradient', { id, gradientUnits: 'userSpaceOnUse', x1: item.from[0], y1: item.from[1], x2: item.to[0], y2: item.to[1] })
          : el('radialGradient', { id, gradientUnits: 'userSpaceOnUse', cx: item.center[0], cy: item.center[1], r: item.radius });
        for (const stop of item.stops) {
          gradient.appendChild(el('stop', { offset: stop.at, 'stop-color': rgba([...stop.color.slice(0, 3), 255]), 'stop-opacity': (stop.color[3] / 255).toFixed(3) }));
        }
        defs.appendChild(gradient);
        parent.appendChild(el('rect', { x: item.x, y: item.y, width: item.w, height: item.h, fill: `url(#${id})` }));
      } else if (item.kind === 'image') {
        parent.appendChild(el('image', { href: item.path, x: item.x, y: item.y, width: item.w, height: item.h, opacity: item.opacity, preserveAspectRatio: 'none' }));
      } else if (item.kind === 'text') {
        const attrs = {
          x: item.x, y: item.baseline,
          'text-anchor': item.anchor === 'middle' ? 'middle' : item.anchor === 'end' ? 'end' : 'start',
          'font-family': `"${item.family}"`, 'font-weight': item.weight, 'font-size': item.size,
          fill: rgba(item.color), 'xml:space': 'preserve',
        };
        // Espacement des lettres : la largeur calculée par Project-On est imposée au navigateur.
        if ((item.letter_spacing || 0) !== 0 || (item.advance_scale || 1) !== 1) {
          attrs.textLength = item.width;
          attrs.lengthAdjust = 'spacing';
        }
        if (item.shadow) {
          const id = `s${ids.n++}`;
          const filter = el('filter', { id, x: '-20%', y: '-50%', width: '140%', height: '200%' });
          filter.appendChild(el('feDropShadow', { dx: item.shadow.dx, dy: item.shadow.dy, stdDeviation: item.shadow.blur / 2, 'flood-color': rgba([...item.shadow.color.slice(0, 3), 255]), 'flood-opacity': (item.shadow.color[3] / 255).toFixed(3) }));
          defs.appendChild(filter);
          attrs.filter = `url(#${id})`;
        }
        const text = el('text', attrs);
        text.style.fontKerning = 'normal';
        text.textContent = item.text;
        parent.appendChild(text);
      } else if (item.kind === 'group') {
        const g = el('g', { opacity: item.opacity });
        const [ox, oy] = item.origin;
        g.setAttribute('transform', `translate(${item.dx} ${item.dy}) translate(${ox} ${oy}) scale(${item.scale}) translate(${-ox} ${-oy})`);
        if (item.clip) {
          const id = `c${ids.n++}`;
          const clip = el('clipPath', { id });
          clip.appendChild(el('rect', { x: item.clip[0], y: item.clip[1], width: item.clip[2], height: item.clip[3] }));
          defs.appendChild(clip);
          g.setAttribute('clip-path', `url(#${id})`);
        }
        if (item.blur > 0) {
          const id = `b${ids.n++}`;
          const filter = el('filter', { id });
          filter.appendChild(el('feGaussianBlur', { stdDeviation: item.blur / 2 }));
          defs.appendChild(filter);
          g.setAttribute('filter', `url(#${id})`);
        }
        draw(g, item.items, defs, ids);
        parent.appendChild(g);
      }
    }
  }

  function build(list) {
    const svg = el('svg', { viewBox: `0 0 ${list.width} ${list.height}`, preserveAspectRatio: 'xMidYMid meet' });
    svg.classList.add('layer');
    const defs = el('defs');
    svg.appendChild(defs);
    svg.appendChild(el('rect', { width: list.width, height: list.height, fill: rgba(list.background) }));
    const ids = { n: 0 };
    draw(svg, list.backdrop, defs, ids);
    draw(svg, list.items, defs, ids);
    draw(svg, list.overlay, defs, ids);
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
