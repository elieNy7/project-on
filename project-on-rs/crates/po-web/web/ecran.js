// Project-On — client d'un écran Web.
//
// Il ne contient aucune logique de mise en page : il dessine, en SVG, la liste d'affichage que
// Project-On a calculée pour la taille de cet écran (lignes déjà coupées et placées au pixel près),
// avec les transitions du vidéoprojecteur (fondu, glissement, zoom, flou, balayage). Il n'envoie
// que sa taille, ses accusés de réception et ses réponses au ping : rien qui pilote.
(() => {
  'use strict';
  const PROTOCOL = __PROTOCOL__;
  const SVG = 'http://www.w3.org/2000/svg';
  const screenName = decodeURIComponent(location.pathname.split('/').filter(Boolean).pop() || 'salle');
  const svg = document.getElementById('stage');
  let ws = null;
  let retryDelay = 500;
  let token = 0;
  let ids = 0;
  let transparent = document.body.classList.contains('transparent');
  const loadedFonts = new Set();

  function el(name, attrs) {
    const node = document.createElementNS(SVG, name);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
    return node;
  }

  // Trois couches, comme le vidéoprojecteur : le fond, le contenu, l'identification.
  const background = el('rect', { width: 1920, height: 1080, fill: 'rgba(0,0,0,0)' });
  const backdropRoot = el('g');
  const contentRoot = el('g', { id: 'content' });
  const overlayRoot = el('g');
  svg.append(background, backdropRoot, contentRoot, overlayRoot);

  // Ce qui est affiché : { seq, width, height, stage, backdropKey, overlayKey }.
  let state = null;
  // La transition en cours : appeler `finish()` la termine aussitôt.
  let running = null;

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

  // Les dessins de la liste d'affichage : les mêmes que ceux de po-render (fenêtre, NDI, HDMI).
  function draw(parent, items, defs) {
    for (const item of items || []) {
      if (item.kind === 'rect') {
        parent.appendChild(el('rect', { x: item.x, y: item.y, width: item.w, height: item.h, rx: item.radius, fill: rgba(item.color) }));
      } else if (item.kind === 'linear_gradient' || item.kind === 'radial_gradient') {
        const id = `g${ids++}`;
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
          const id = `s${ids++}`;
          const filter = el('filter', { id, x: '-20%', y: '-50%', width: '140%', height: '200%' });
          filter.appendChild(el('feDropShadow', { dx: item.shadow.dx, dy: item.shadow.dy, stdDeviation: item.shadow.blur / 2, 'flood-color': rgba([...item.shadow.color.slice(0, 3), 255]), 'flood-opacity': (item.shadow.color[3] / 255).toFixed(3) }));
          defs.appendChild(filter);
          attrs.filter = `url(#${id})`;
        }
        // Le contour (sous-titres « contour ») : un trait dessiné sous les lettres.
        if (item.outline) {
          attrs.stroke = rgba(item.outline.color);
          attrs['stroke-width'] = item.outline.width * 2;
          attrs['stroke-linejoin'] = 'round';
          attrs['paint-order'] = 'stroke';
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
          const id = `c${ids++}`;
          const clip = el('clipPath', { id });
          clip.appendChild(el('rect', { x: item.clip[0], y: item.clip[1], width: item.clip[2], height: item.clip[3] }));
          defs.appendChild(clip);
          g.setAttribute('clip-path', `url(#${id})`);
        }
        if (item.blur > 0) {
          const id = `b${ids++}`;
          const filter = el('filter', { id });
          filter.appendChild(el('feGaussianBlur', { stdDeviation: item.blur / 2 }));
          defs.appendChild(filter);
          g.setAttribute('filter', `url(#${id})`);
        }
        draw(g, item.items, defs);
        parent.appendChild(g);
      }
    }
  }

  // Une couche dessinée : un groupe qui porte ses propres définitions (dégradés, ombres), retirées
  // avec lui.
  function layer(items) {
    const g = el('g');
    const defs = el('defs');
    g.appendChild(defs);
    draw(g, items, defs);
    return g;
  }

  // ── Les transitions : `po_layout::transition` (Rust), à l'identique. ─────────────────────────

  function ease(t) {
    t = Math.min(1, Math.max(0, t));
    const cubic = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    const p = Math.min(1, Math.max(0, cubic));
    return p * p * p * (p * (p * 6 - 15) + 10);
  }

  function vector(direction) {
    return { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] }[direction] || [0, -1];
  }

  function blurRadius(animation) {
    return Math.min(40, Math.max(10, Math.floor(animation.duration_ms / 16)));
  }

  function revealClip([x, y, w, h], dx, dy, e) {
    if (dy < 0) return [x, y + h - h * e, w, h * e];
    if (dy > 0) return [x, y, w, h * e];
    if (dx < 0) return [x + w - w * e, y, w * e, h];
    return [x, y, w * e, h];
  }

  function hiddenClip([x, y, w, h], dx, dy, e) {
    if (dy < 0) return [x, y, w, h - h * e];
    if (dy > 0) return [x, y + h * e, w, h - h * e];
    if (dx < 0) return [x, y, w - w * e, h];
    return [x + w * e, y, w - w * e, h];
  }

  function place(layer, opacity, extra) {
    return Object.assign({ layer, opacity, dx: 0, dy: 0, scale: 1, origin: [0, 0], blur: 0, clip: null }, extra || {});
  }

  // Les couches de contenu au temps t. Sur un écran transparent (bandeau), le glissement est court
  // et fondu : traverser toute la vidéo serait trop.
  function plan(stage, width, height, animation, t) {
    const e = ease(t);
    const [dx, dy] = vector(animation.direction);
    const center = [stage[0] + stage[2] / 2, stage[1] + stage[3] / 2];
    let places;
    switch (animation.kind) {
      case 'fade':
        places = [place('from', 1 - e), place('to', e)];
        break;
      case 'slide':
        if (transparent) {
          const d = height * 0.06;
          places = [place('from', 1 - e, { dx: dx * d * e, dy: dy * d * e }), place('to', e, { dx: -dx * d * (1 - e), dy: -dy * d * (1 - e) })];
        } else {
          places = [place('from', 1, { dx: dx * width * e, dy: dy * height * e }), place('to', 1, { dx: -dx * width * (1 - e), dy: -dy * height * (1 - e) })];
        }
        break;
      case 'scale':
        places = [place('from', 1 - e, { scale: 1 + 0.06 * e, origin: center }), place('to', e, { scale: 0.94 + 0.06 * e, origin: center })];
        break;
      case 'blur': {
        const radius = blurRadius(animation);
        if (e < 0.5) {
          const p = e / 0.5;
          places = [place('from', 1 - p), place('from', p, { blur: radius })];
        } else {
          const p = (e - 0.5) / 0.5;
          places = [place('to', 1 - p, { blur: radius }), place('to', p)];
        }
        break;
      }
      case 'reveal':
        places = [place('from', 1, { clip: hiddenClip(stage, dx, dy, e) }), place('to', 1, { clip: revealClip(stage, dx, dy, e) })];
        break;
      default:
        places = [place('to', 1)];
    }
    return places.filter((p) => p.opacity > 0.004);
  }

  // Un support animé : un groupe qui reçoit opacité, déplacement, échelle, flou et découpe.
  function holder(content, blur) {
    const g = el('g', { opacity: 0 });
    const defs = el('defs');
    const clipId = `c${ids++}`;
    const clip = el('clipPath', { id: clipId });
    const clipRect = el('rect');
    clip.appendChild(clipRect);
    defs.appendChild(clip);
    if (blur > 0) {
      const id = `b${ids++}`;
      const filter = el('filter', { id, x: '-10%', y: '-10%', width: '120%', height: '120%' });
      filter.appendChild(el('feGaussianBlur', { stdDeviation: blur / 2 }));
      defs.appendChild(filter);
      g.setAttribute('filter', `url(#${id})`);
    }
    g.appendChild(defs);
    g.appendChild(content);
    return {
      g,
      set(p) {
        g.setAttribute('opacity', p.opacity.toFixed(4));
        const [ox, oy] = p.origin;
        g.setAttribute('transform', `translate(${p.dx} ${p.dy}) translate(${ox} ${oy}) scale(${p.scale}) translate(${-ox} ${-oy})`);
        if (p.clip) {
          clipRect.setAttribute('x', p.clip[0]);
          clipRect.setAttribute('y', p.clip[1]);
          clipRect.setAttribute('width', Math.max(0, p.clip[2]));
          clipRect.setAttribute('height', Math.max(0, p.clip[3]));
          g.setAttribute('clip-path', `url(#${clipId})`);
        } else {
          g.removeAttribute('clip-path');
        }
      },
      hide() { g.setAttribute('opacity', 0); },
    };
  }

  // Remplace sans transition.
  function replace(root, content) {
    root.replaceChildren(content);
  }

  // Joue la transition de `from` vers `to` (les contenus des trois couches).
  function transition(animation, fresh, stage, width, height) {
    const duration = Math.max(1, animation.duration_ms);
    const fromContent = contentRoot.firstChild;
    const holders = new Map();
    const get = (layer, blur) => {
      const key = `${layer}:${blur > 0}`;
      if (!holders.has(key)) {
        const source = layer === 'from' ? fromContent : fresh.content;
        if (!source) return null;
        // Le contenu net garde le nœud ; le flou en dessine une copie.
        const node = holders.has(`${layer}:${blur <= 0}`) || blur > 0 ? source.cloneNode(true) : source;
        const h = holder(node, blur);
        holders.set(key, h);
      }
      return holders.get(key);
    };
    // Les supports nets d'abord (ils gardent les nœuds d'origine).
    get('from', 0);
    get('to', 0);
    if (animation.kind === 'blur') {
      get('from', blurRadius(animation));
      get('to', blurRadius(animation));
    }
    contentRoot.replaceChildren(...[...holders.values()].map((h) => h.g));
    // Le fond et l'identification passent en fondu s'ils changent.
    const fades = [];
    for (const [root, next] of [[backdropRoot, fresh.backdrop], [overlayRoot, fresh.overlay]]) {
      if (!next) continue;
      next.setAttribute('opacity', 0);
      root.appendChild(next);
      fades.push({ root, next });
    }
    const started = performance.now();
    let frame = 0;
    let safety = 0;
    const finish = () => {
      cancelAnimationFrame(frame);
      clearTimeout(safety);
      running = null;
      contentRoot.replaceChildren(fresh.content);
      for (const { root, next } of fades) {
        next.removeAttribute('opacity');
        root.replaceChildren(next);
      }
    };
    const tick = (now) => {
      const t = Math.min(1, (now - started) / duration);
      for (const h of holders.values()) h.hide();
      for (const p of plan(stage, width, height, animation, t)) {
        const h = holders.get(`${p.layer}:${p.blur > 0}`);
        if (h) h.set(p);
      }
      const e = ease(t);
      for (const { next } of fades) next.setAttribute('opacity', e.toFixed(4));
      if (t >= 1) finish();
      else frame = requestAnimationFrame(tick);
    };
    running = { finish };
    // Un navigateur qui ralentit ses images (onglet caché, machine chargée) termine quand même la
    // transition à l'heure : jamais l'ancien slide figé à l'écran.
    safety = setTimeout(finish, duration + 150);
    tick(started);
  }

  async function show(message) {
    const mine = ++token;
    await ensureFonts(message.list);
    if (mine !== token) return; // une image plus récente est arrivée pendant le chargement
    if (running) running.finish();
    const list = message.list;
    const resized = !state || state.width !== list.width || state.height !== list.height;
    svg.setAttribute('viewBox', `0 0 ${list.width} ${list.height}`);
    background.setAttribute('width', list.width);
    background.setAttribute('height', list.height);
    background.setAttribute('fill', rgba(list.background));
    const backdropKey = JSON.stringify(list.backdrop);
    const overlayKey = JSON.stringify(list.overlay);
    const contentKey = JSON.stringify(list.items);
    // Même slide, même contenu (seul un habillage bouge) : le contenu n'est pas redessiné.
    const sameContent = !resized && state.seq === message.seq && state.contentKey === contentKey;
    const fresh = {
      content: sameContent ? null : layer(list.items),
      backdrop: resized || state.backdropKey !== backdropKey ? layer(list.backdrop) : null,
      overlay: resized || state.overlayKey !== overlayKey ? layer(list.overlay) : null,
    };
    const animation = message.animation;
    const animate = !resized && state.seq !== message.seq && animation && animation.kind !== 'none'
      && animation.duration_ms > 0 && !document.hidden;
    contentRoot.classList.toggle('hidden', !!message.hidden);
    if (animate) {
      transition(animation, fresh, list.stage, list.width, list.height);
    } else {
      if (fresh.content) replace(contentRoot, fresh.content);
      if (fresh.backdrop) replace(backdropRoot, fresh.backdrop);
      if (fresh.overlay) replace(overlayRoot, fresh.overlay);
    }
    state = { seq: message.seq, width: list.width, height: list.height, backdropKey, overlayKey, contentKey };
    document.body.classList.add('ready');
    requestAnimationFrame(() => send({ type: 'ack', seq: message.seq }));
  }

  function hello(message) {
    if (message.version !== PROTOCOL) {
      // Project-On a été mis à jour : la page se recharge (une fois par minute au plus).
      const last = Number(sessionStorage.getItem('po-reload') || 0);
      if (Date.now() - last > 60000) {
        sessionStorage.setItem('po-reload', String(Date.now()));
        location.reload();
      }
      return;
    }
    transparent = !!message.transparent;
    document.body.classList.toggle('transparent', transparent);
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
      else if (message.type === 'hello') hello(message);
    };
    ws.onclose = () => {
      // La dernière image reste à l'écran ; nouvelle tentative de 0,5 à 5 s.
      document.body.classList.add('offline');
      setTimeout(connect, retryDelay + Math.random() * 200);
      retryDelay = Math.min(retryDelay * 2, 5000);
    };
    ws.onerror = () => ws.close();
  }

  // Un téléviseur ou une tablette ne doit pas se mettre en veille pendant le culte.
  async function keepAwake() {
    try {
      if (navigator.wakeLock && document.visibilityState === 'visible') await navigator.wakeLock.request('screen');
    } catch { /* non disponible (adresse non sécurisée) : sans effet */ }
  }
  document.addEventListener('visibilitychange', keepAwake);

  // Double-clic : plein écran.
  document.addEventListener('dblclick', () => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else document.documentElement.requestFullscreen().catch(() => {});
  });

  let resizeTimer = 0;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(announceSize, 150);
  });
  keepAwake();
  connect();
})();
