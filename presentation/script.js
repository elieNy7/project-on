let currentConfig = {};
let lastSlidePayload = null;
let lastConfigPayload = null;
let isAnimating = false;
let pendingSlidePayload = null;

async function readJson(url) {
  try {
    const res = await fetch(url + '?t=' + Date.now(), { 
      cache: 'no-store',
      headers: { 'Cache-Control': 'no-cache' }
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function applyConfig(cfg) {
  if (!cfg) return;
  const root = document.documentElement;
  currentConfig = { ...currentConfig, ...cfg };
  
  if (cfg.font_family) {
    root.style.setProperty('--font-family', `'${cfg.font_family}', 'Poppins', system-ui, sans-serif`);
  }
  
  if (cfg.text_size) {
    root.style.setProperty('--base-text-size', cfg.text_size + 'px');
    root.style.setProperty('--text-size', cfg.text_size + 'px');
  }
  if (cfg.ref_size) root.style.setProperty('--ref-size', cfg.ref_size + 'px');
  if (cfg.padding !== undefined) root.style.setProperty('--padding', cfg.padding + 'px');
  const configuredWidth = cfg.content_width ?? cfg.max_width;
  if (configuredWidth !== undefined) {
    const maxWidth = Math.max(40, Math.min(100, Number(configuredWidth) || 88));
    root.style.setProperty('--shell-width', `calc(${maxWidth}vw - (var(--padding) * 2))`);
  }
  if (cfg.content_height !== undefined) {
    const maxHeight = Math.max(35, Math.min(100, Number(cfg.content_height) || 82));
    root.style.setProperty('--shell-height', `calc(${maxHeight}dvh - (var(--padding) * 2))`);
  }
  
  if (cfg.align) {
    root.style.setProperty('--align', cfg.align);
    const alignFlex = (cfg.align === 'left') ? 'flex-start' : (cfg.align === 'right' ? 'flex-end' : 'center');
    root.style.setProperty('--align-flex', alignFlex);
  }
  
  if (cfg.text_color) root.style.setProperty('--text-color', cfg.text_color);
  if (cfg.ref_color) root.style.setProperty('--ref-color', cfg.ref_color);
  if (cfg.font_weight) root.style.setProperty('--font-weight', cfg.font_weight);
  if (cfg.line_height) root.style.setProperty('--line-height', cfg.line_height);
  if (cfg.letter_spacing !== undefined) root.style.setProperty('--letter-spacing', cfg.letter_spacing + 'px');
  if (cfg.bg_color) root.style.setProperty('--bg-color', cfg.bg_color);
  if (cfg.bg_color_2) root.style.setProperty('--bg-color-accent', cfg.bg_color_2);

  const rootEl = document.getElementById('root');
  if (rootEl) {
    rootEl.classList.remove('style-cinematic', 'style-clean', 'style-glass', 'style-card', 'style-split');
    const slideStyle = cfg.slide_style || 'cinematic';
    rootEl.classList.add(`style-${slideStyle}`);
  }

  const frameOpacity = Math.max(0, Math.min(0.8, Number(cfg.frame_opacity ?? 0.18)));
  const frameRadius = Math.max(0, Math.min(80, Number(cfg.frame_radius ?? 28)));
  const slideStyle = cfg.slide_style || 'cinematic';
  const forceFrame = ['glass', 'card', 'split'].includes(slideStyle);
  const hasFrame = cfg.frame_enabled === true || forceFrame;
  if (hasFrame) {
    const alpha = slideStyle === 'glass' ? Math.max(frameOpacity, 0.16) : frameOpacity;
    root.style.setProperty('--frame-bg', `rgba(7, 13, 24, ${alpha.toFixed(2)})`);
    root.style.setProperty('--frame-border', `rgba(255, 255, 255, ${Math.min(0.22, alpha + 0.05).toFixed(2)})`);
    root.style.setProperty('--frame-radius', `${frameRadius}px`);
    root.style.setProperty('--frame-shadow', '0 28px 80px rgba(0, 0, 0, 0.34)');
    root.style.setProperty('--frame-backdrop', slideStyle === 'glass' ? 'blur(18px) saturate(135%)' : 'none');
  } else {
    root.style.setProperty('--frame-bg', 'transparent');
    root.style.setProperty('--frame-border', 'transparent');
    root.style.setProperty('--frame-radius', '0px');
    root.style.setProperty('--frame-shadow', 'none');
    root.style.setProperty('--frame-backdrop', 'none');
  }

  const textEl = document.getElementById('text');
  if (textEl) {
    textEl.style.textTransform = cfg.uppercase ? 'uppercase' : 'none';
  }

  const refContainer = document.getElementById('ref-container');
  if (refContainer) {
    const show = cfg.show_reference !== false;
    refContainer.classList.toggle('hidden', !show);
  }

  const slide = document.getElementById('slide');
  if (slide) {
    slide.style.justifyContent = cfg.position === 'top'
      ? 'flex-start'
      : cfg.position === 'bottom'
        ? 'flex-end'
        : 'center';
  }

  const content = document.querySelector('.content');
  if (content) {
    const refTop = (cfg.reference_position || 'bottom') === 'top';
    content.classList.toggle('ref-top', refTop);
    content.classList.toggle('ref-bottom', !refTop);
  }
}

function fitTextToStage(textEl, shellEl, baseSize) {
  if (!textEl || !shellEl) return;

  const root = document.documentElement;
  const minSize = 30;
  const shellBounds = shellEl.getBoundingClientRect();
  const maxHeight = Math.max(320, Math.min(window.innerHeight - 48, shellBounds.height || window.innerHeight));
  const maxWidth = Math.max(420, Math.min(window.innerWidth - 48, shellBounds.width || window.innerWidth));
  let size = Math.max(minSize, Math.round(baseSize));

  root.style.setProperty('--text-size', `${size}px`);
  for (let i = 0; i < 28; i += 1) {
    const tooTall = shellEl.scrollHeight > maxHeight;
    const tooWide = shellEl.scrollWidth > maxWidth || textEl.scrollWidth > textEl.clientWidth + 2;
    if ((!tooTall && !tooWide) || size <= minSize) break;
    size = Math.max(minSize, size - 2);
    root.style.setProperty('--text-size', `${size}px`);
  }
}

async function updateSlide(payload) {
  if (isAnimating) {
    pendingSlidePayload = payload;
    return;
  }
  isAnimating = true;
  pendingSlidePayload = null;

  const slide = document.getElementById('slide');
  const stageShell = document.getElementById('stage-shell');
  const textEl = document.getElementById('text');
  const refEl = document.getElementById('ref');

  slide.classList.remove('visible');
  await new Promise(r => setTimeout(r, 320));

  const text = payload.text || '';
  const reference = payload.reference || '';
  const visual = payload.image || payload.background || '';
  const baseSize = Number.parseFloat(
    getComputedStyle(document.documentElement).getPropertyValue('--base-text-size')
  ) || 72;
  document.documentElement.style.setProperty('--text-size', `${Math.max(30, Math.round(baseSize))}px`);

  textEl.textContent = text;
  refEl.textContent = reference;
  const refContainer = document.getElementById('ref-container');
  if (refContainer) {
    refContainer.classList.toggle('hidden', !reference.trim());
  }

  if (visual) {
    slide.style.backgroundImage = `url('${visual}')`;
  } else {
    slide.style.backgroundImage = '';
  }

  const isTextlessVisual = !text.trim() && !!visual;
  slide.classList.toggle('image-slide', !!visual);
  slide.classList.toggle('textless', isTextlessVisual);
  if (stageShell) {
    stageShell.style.display = isTextlessVisual ? 'none' : '';
    if (!isTextlessVisual) fitTextToStage(textEl, stageShell, baseSize);
  }

  slide.classList.add('visible');

  await new Promise(r => setTimeout(r, 360));
  isAnimating = false;

  if (pendingSlidePayload) {
    const nextPayload = pendingSlidePayload;
    pendingSlidePayload = null;
    await updateSlide(nextPayload);
  }
}

async function tick() {
  // Config handling
  const cfg = await readJson('config.json');
  if (cfg) {
    const s = JSON.stringify(cfg);
    if (s !== lastConfigPayload) {
      lastConfigPayload = s;
      applyConfig(cfg);
    }
  }

  // Slide handling
  const payload = await readJson('slide.json');
  if (payload) {
    const s = JSON.stringify(payload);
    if (s !== lastSlidePayload) {
      lastSlidePayload = s;
      await updateSlide(payload);
    }
  }
}

// Tick periodically
setInterval(tick, 200);
tick();
