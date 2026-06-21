/**
 * Project-On OBS Broadcast Script
 * Broadcast transitions and premium source badge.
 */

let lastSlideStr = '';
let currentConfig = {};
let transitionToken = 0;

/* ── Color helpers ───────────────────────────────────────────── */
function applyAlpha(colorStr, alpha) {
    if (alpha === undefined || alpha === null) return colorStr;
    const a = Math.max(0, Math.min(1, parseFloat(alpha)));

    const rgbaMatch = colorStr.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*[\d.]+)?\s*\)/);
    if (rgbaMatch) {
        return `rgba(${rgbaMatch[1]}, ${rgbaMatch[2]}, ${rgbaMatch[3]}, ${a.toFixed(2)})`;
    }

    const hexMatch = colorStr.match(/^#([0-9a-fA-F]+)$/);
    if (hexMatch) {
        let hex = hexMatch[1];
        let r, g, b;
        if (hex.length === 3 || hex.length === 4) {
            r = parseInt(hex[0] + hex[0], 16);
            g = parseInt(hex[1] + hex[1], 16);
            b = parseInt(hex[2] + hex[2], 16);
        } else if (hex.length >= 6) {
            r = parseInt(hex.substring(0, 2), 16);
            g = parseInt(hex.substring(2, 4), 16);
            b = parseInt(hex.substring(4, 6), 16);
        } else {
            return colorStr;
        }
        return `rgba(${r}, ${g}, ${b}, ${a.toFixed(2)})`;
    }
    return colorStr;
}

/* ── Config Application ──────────────────────────────────────── */
function applyConfig(cfg) {
    if (!cfg) return;
    currentConfig = { ...currentConfig, ...cfg };
    const root = document.documentElement;
    const rootEl = document.getElementById('root');
    const lowerThird = document.getElementById('lower-third');
    if (!rootEl || !lowerThird) return;

    const body = lowerThird.querySelector('.lt-body');

    root.style.setProperty('--overall-opacity', cfg.opacity ?? 1.0);

    // Typography
    root.style.setProperty('--font-family', `'${cfg.font_family || 'Poppins'}', system-ui, sans-serif`);
    root.style.setProperty('--font-weight', cfg.font_weight || '600');
    root.style.setProperty('--text-size', `${cfg.text_size || 52}px`);
    root.style.setProperty('--base-text-size', `${cfg.text_size || 52}px`);
    root.style.setProperty('--ref-size', `${cfg.ref_size || 20}px`);
    root.style.setProperty('--letter-spacing', `${cfg.letter_spacing || 0}px`);
    root.style.setProperty('--line-height', cfg.line_height || 1.3);
    root.style.setProperty('--text-transform', cfg.text_transform || 'none');

    // Background
    if (cfg.bg_enabled !== false) {
        const bgOpacity = cfg.bg_opacity ?? 1.0;
        const rawBg1 = cfg.bg_color || 'rgba(15, 23, 42, 0.82)';
        const rawBg2 = cfg.bg_gradient_enabled
            ? (cfg.bg_color_2 || 'rgba(2, 6, 23, 0.92)')
            : rawBg1;

        root.style.setProperty('--bg-color', applyAlpha(rawBg1, bgOpacity));
        root.style.setProperty('--bg-color-2', applyAlpha(rawBg2, bgOpacity));

        if (cfg.bg_gradient_angle !== undefined) {
            root.style.setProperty('--gradient-direction', `${cfg.bg_gradient_angle}deg`);
        }
        if (body) body.classList.remove('bg-hidden');
    } else {
        if (body) body.classList.add('bg-hidden');
    }

    // Background image confined to the lower-third band (app settings).
    // Only when the user chose "image" mode AND a path is set.
    const ltBgImage = document.getElementById('lt-bg-image');
    const ltBody = lowerThird.querySelector('.lt-body');
    if (ltBgImage) {
        const useImage = cfg.bg_mode === 'image';
        const bgImg = (cfg.bg_image || '').trim();
        if (useImage && bgImg) {
            const bgBaseUrl = window.location.protocol === 'file:' ? 'http://127.0.0.1:8080' : '';
            ltBgImage.style.backgroundImage = `url('${bgBaseUrl}/api/bg-image?v=${encodeURIComponent(bgImg)}')`;
            ltBgImage.style.backgroundSize = cfg.bg_image_fit === 'contain' ? 'contain' : 'cover';
            ltBgImage.classList.add('visible');
            if (ltBody) ltBody.classList.add('has-bg-image');
        } else {
            ltBgImage.style.backgroundImage = '';
            ltBgImage.classList.remove('visible');
            if (ltBody) ltBody.classList.remove('has-bg-image');
        }
    }

    root.style.setProperty('--bg-blur', cfg.bg_blur ? `${cfg.bg_blur_amount || 20}px` : '0px');
    root.style.setProperty('--text-color', cfg.text_color || '#ffffff');
    root.style.setProperty('--ref-color', cfg.ref_color || 'rgba(255, 255, 255, 0.82)');

    if (cfg.accent_color) {
        root.style.setProperty('--accent-color', cfg.accent_color);
    }

    // Layout
    root.style.setProperty('--padding-h', `${cfg.padding_horizontal || 52}px`);
    root.style.setProperty('--padding-v', `${cfg.padding_vertical || 30}px`);
    root.style.setProperty('--max-width', `${cfg.max_width || 85}%`);
    root.style.setProperty('--border-radius', `${cfg.border_radius || 14}px`);

    // Stroke
    if (cfg.text_stroke) {
        root.style.setProperty('--stroke-width', `${cfg.stroke_width || 1}px`);
        root.style.setProperty('--stroke-color', cfg.stroke_color || 'rgba(0,0,0,0.8)');
    } else {
        root.style.setProperty('--stroke-width', '0px');
        root.style.setProperty('--stroke-color', 'transparent');
    }

    // Shadow
    if (cfg.text_shadow !== false) {
        const sc = cfg.shadow_color || 'rgba(0,0,0,0.6)';
        const sb = cfg.shadow_blur || 8;
        root.style.setProperty('--text-shadow', `0 2px ${sb}px ${sc}`);
    } else {
        root.style.setProperty('--text-shadow', 'none');
    }

    // Position & Align
    rootEl.classList.remove('position-top', 'position-center', 'align-left', 'align-center');
    if (cfg.position === 'top') rootEl.classList.add('position-top');
    else if (cfg.position === 'center') rootEl.classList.add('position-center');

    const isLeft = cfg.align === 'left';
    rootEl.classList.add(isLeft ? 'align-left' : 'align-center');
    root.style.setProperty('--align-flex', isLeft ? 'flex-start' : 'center');
    root.style.setProperty('--align', isLeft ? 'left' : 'center');

    const backgroundEnabled = cfg.bg_enabled !== false;
    rootEl.classList.toggle('background-disabled', !backgroundEnabled);

    // Reference visibility
    const refBox = document.getElementById('ref-box');
    const divider = document.getElementById('divider');
    if (refBox) refBox.classList.toggle('hidden', cfg.show_reference === false);
    if (divider) divider.classList.toggle('hidden', cfg.show_reference === false);

    // Accent strip hidden when background is off
    const accentStrip = document.getElementById('accent-strip');
    if (accentStrip) {
        accentStrip.style.display = backgroundEnabled ? '' : 'none';
    }
}

function resetSourceTextLayout() {
    const root = document.documentElement;
    root.style.removeProperty('--hymn-padding-v');
    root.style.removeProperty('--hymn-padding-h');
    root.style.removeProperty('--hymn-gap');
    root.style.removeProperty('--hymn-line-height');
}

function fitTextToViewport(textEl, refEl, bodyEl, baseTextSize) {
    if (!textEl || !bodyEl) return;

    const root = document.documentElement;
    const minSize = 24;
    const maxHeight = Math.max(220, window.innerHeight - 112);
    const maxWidth = Math.max(360, window.innerWidth - 112);
    let size = Math.max(minSize, Math.round(baseTextSize));

    root.style.setProperty('--text-size', `${size}px`);
    for (let i = 0; i < 24; i += 1) {
        const tooTall = bodyEl.scrollHeight > maxHeight;
        const tooWide = bodyEl.scrollWidth > maxWidth || textEl.scrollWidth > textEl.clientWidth + 2;
        if ((!tooTall && !tooWide) || size <= minSize) break;
        size = Math.max(minSize, size - 2);
        root.style.setProperty('--text-size', `${size}px`);
    }

    if (refEl) {
        refEl.style.maxWidth = `${maxWidth}px`;
    }
}

function getTransitionSettings() {
    const enabled = currentConfig.animation_enabled !== false;
    const type = currentConfig.animation_type || 'auto';
    const direction = currentConfig.animation_direction || 'up';
    const duration = Number(currentConfig.animation_duration || 0);

    return {
        enabled: enabled && duration > 0 && type !== 'none',
        type,
        direction,
        duration,
    };
}

function resolveSourceTransition(source, transition) {
    if (transition.type !== 'auto') return transition;

    const presets = {
        bible: { type: 'fade', direction: 'up', duration: Math.max(transition.duration || 520, 420) },
        hymn: { type: 'slide', direction: 'up', duration: Math.max(transition.duration || 520, 560) },
        sermon: { type: 'fade', direction: 'up', duration: Math.max(transition.duration || 520, 420) },
        expose: { type: 'slide', direction: 'right', duration: Math.max(transition.duration || 520, 520) },
        custom: { type: 'scale', direction: 'up', duration: Math.max(transition.duration || 520, 460) },
        image: { type: 'fade', direction: 'up', duration: Math.max(transition.duration || 520, 700) },
    };

    return {
        ...transition,
        ...(presets[source] || { type: 'fade', direction: 'up', duration: Math.max(transition.duration || 520, 420) }),
    };
}

function getDirectionalOffset(direction, distance = 54) {
    switch (direction) {
        case 'down': return { x: 0, y: distance };
        case 'left': return { x: -distance, y: 0 };
        case 'right': return { x: distance, y: 0 };
        case 'up':
        default:
            return { x: 0, y: -distance };
    }
}

function resetAnimatedState(element) {
    if (!element) return;
    if (typeof element.getAnimations === 'function') {
        element.getAnimations().forEach((animation) => animation.cancel());
    }
    element.style.opacity = '';
    element.style.transform = '';
    element.style.filter = '';
    element.style.clipPath = '';
}

function resetSlideAnimatedState(...elements) {
    elements.forEach(resetAnimatedState);
}

async function animateElement(element, phase, settings, token) {
    if (!element || !settings.enabled || typeof element.animate !== 'function') {
        return;
    }

    const { type, direction, duration } = settings;
    const { x, y } = getDirectionalOffset(direction);
    let frames;

    switch (type) {
        case 'slide':
            frames = phase === 'in'
                ? [
                    { opacity: 0, transform: `translate(${x}px, ${y}px)` },
                    { opacity: 1, transform: 'translate(0px, 0px)' },
                ]
                : [
                    { opacity: 1, transform: 'translate(0px, 0px)' },
                    { opacity: 0, transform: `translate(${-x * 0.6}px, ${-y * 0.6}px)` },
                ];
            break;
        case 'scale':
            frames = phase === 'in'
                ? [
                    { opacity: 0, transform: 'scale(0.94)' },
                    { opacity: 1, transform: 'scale(1)' },
                ]
                : [
                    { opacity: 1, transform: 'scale(1)' },
                    { opacity: 0, transform: 'scale(1.04)' },
                ];
            break;
        case 'reveal': {
            const clipFrom = direction === 'left'
                ? 'inset(0 100% 0 0 round 24px)'
                : direction === 'right'
                    ? 'inset(0 0 0 100% round 24px)'
                    : direction === 'down'
                        ? 'inset(0 0 100% 0 round 24px)'
                        : 'inset(100% 0 0 0 round 24px)';
            const clipTo = 'inset(0 0 0 0 round 24px)';
            frames = phase === 'in'
                ? [
                    { opacity: 0.2, clipPath: clipFrom },
                    { opacity: 1, clipPath: clipTo },
                ]
                : [
                    { opacity: 1, clipPath: clipTo },
                    { opacity: 0.1, clipPath: clipFrom },
                ];
            break;
        }
        case 'fade':
            frames = phase === 'in'
                ? [{ opacity: 0 }, { opacity: 1 }]
                : [{ opacity: 1 }, { opacity: 0 }];
            break;
        case 'blur':
        default:
            frames = phase === 'in'
                ? [
                    { opacity: 0, filter: 'blur(6px)', transform: 'scale(1.006)' },
                    { opacity: 1, filter: 'blur(0px)', transform: 'scale(1)' },
                ]
                : [
                    { opacity: 1, filter: 'blur(0px)', transform: 'scale(1)' },
                    { opacity: 0, filter: 'blur(4px)', transform: 'scale(0.996)' },
                ];
            break;
    }

    const easing = phase === 'in'
        ? 'cubic-bezier(0.16, 1, 0.3, 1)'
        : 'cubic-bezier(0.7, 0, 0.84, 0)';

    const animation = element.animate(frames, {
        duration,
        easing,
        fill: 'forwards',
    });
    try {
        await animation.finished;
    } catch {
        // Ignore interrupted transitions.
    } finally {
        if (token === undefined || token === transitionToken) {
            resetAnimatedState(element);
        }
    }
}

function getSourcePresentation(source) {
    switch (source) {
        case 'bible':
            return {
                label: 'Bible',
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
            };
        case 'hymn':
            return {
                label: 'Cantique',
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>',
            };
        case 'sermon':
            return {
                label: 'Prédication',
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>',
            };
        case 'expose':
            return {
                label: 'Exposé',
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4h18"></path><path d="M8 4v16"></path><path d="M8 10h10"></path><path d="M8 16h7"></path></svg>',
            };
        case 'image':
            return {
                label: 'Visuel',
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"></rect><circle cx="8.5" cy="9.5" r="1.5"></circle><path d="M21 15l-5-5L5 20"></path></svg>',
            };
        case 'custom':
        default:
            return {
                label: 'Projection',
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg>',
            };
    }
}

/* ── Slide Management ────────────────────────────────────────── */
async function setSlide(payload) {
    const slideStr = JSON.stringify(payload);
    if (slideStr === lastSlideStr) return;
    lastSlideStr = slideStr;
    const localToken = ++transitionToken;

    const textEl = document.getElementById('text');
    const refEl = document.getElementById('ref');
    const lowerThird = document.getElementById('lower-third');
    const divider = document.getElementById('divider');
    const imgContainer = document.getElementById('image-container');
    const refIcon = document.getElementById('ref-icon');
    const refBox = document.getElementById('ref-box');
    const sourceKicker = document.getElementById('source-kicker');
    const sourceKickerIcon = document.getElementById('source-kicker-icon');
    const sourceKickerLabel = document.getElementById('source-kicker-label');
    const innerWrapper = document.getElementById('inner-wrapper');
    const transition = resolveSourceTransition(payload?.source, getTransitionSettings());
    const textPanelVisible = !!(
        lowerThird
        && lowerThird.classList.contains('visible')
        && innerWrapper
        && !innerWrapper.classList.contains('content-hidden')
    );
    resetSlideAnimatedState(innerWrapper);

    const hasText = payload && payload.text && payload.text.trim().length > 0;
    const imagePath = (payload && (payload.image || payload.image_path)) || '';
    const hasImage = !!(imagePath && imagePath.trim().length > 0);
    if (imgContainer) {
        imgContainer.classList.toggle('image-only', hasImage && !hasText);
    }

    if (!payload || payload.hidden || (!hasText && !hasImage)) {
        if (textPanelVisible) {
            await animateElement(innerWrapper, 'out', transition, localToken);
        }
        if (localToken !== transitionToken) return;
        resetSlideAnimatedState(innerWrapper);
        if (innerWrapper) innerWrapper.classList.add('content-hidden');
        if (lowerThird) {
            lowerThird.classList.remove('visible');
            lowerThird.className = lowerThird.className.replace(/source-\S+/g, '');
        }
        if (imgContainer) {
            imgContainer.classList.remove('visible');
            imgContainer.style.backgroundImage = '';
        }
        return;
    }

    if (imgContainer) {
        resetAnimatedState(imgContainer);
        if (hasImage) {
            const baseUrl = window.location.protocol === 'file:' ? 'http://127.0.0.1:8080' : '';
            imgContainer.style.backgroundImage = `url('${baseUrl}/api/image?ts=${Date.now()}')`;
            imgContainer.classList.add('visible');
        } else {
            imgContainer.classList.remove('visible');
            imgContainer.style.backgroundImage = '';
        }
    }

    if (!hasText) {
        if (textPanelVisible) {
            await animateElement(innerWrapper, 'out', transition, localToken);
            if (localToken !== transitionToken) return;
        }
        resetSlideAnimatedState(innerWrapper);
        if (innerWrapper) innerWrapper.classList.add('content-hidden');
        if (lowerThird) {
            lowerThird.classList.remove('visible');
        }
        return;
    }

    const text = payload.text || '';
    resetSourceTextLayout();
    const textDensity = Math.max(text.length, (text.match(/\n/g) || []).length * 44);
    const baseTextSize = parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue('--base-text-size')
    ) || 52;
    let densityFactor = 1;
    if (payload.source === 'hymn') {
        if (textDensity > 520) densityFactor = 0.66;
        else if (textDensity > 380) densityFactor = 0.76;
        else if (textDensity > 260) densityFactor = 0.86;
        else if (textDensity > 180) densityFactor = 0.94;
    } else {
        if (textDensity > 420) densityFactor = 0.72;
        else if (textDensity > 320) densityFactor = 0.8;
        else if (textDensity > 220) densityFactor = 0.9;
    }
    document.documentElement.style.setProperty(
        '--text-size',
        `${Math.max(28, Math.round(baseTextSize * densityFactor))}px`
    );
    const fittedBaseSize = Math.max(28, Math.round(baseTextSize * densityFactor));

    if (textPanelVisible) {
        await animateElement(innerWrapper, 'out', transition, localToken);
        if (localToken !== transitionToken) return;
    }
    resetSlideAnimatedState(innerWrapper);
    if (innerWrapper) innerWrapper.classList.add('content-hidden');

    if (lowerThird) {
        lowerThird.className = lowerThird.className.replace(/source-\S+/g, '');
        if (payload.source) {
            lowerThird.classList.add(`source-${payload.source}`);
        }
    }

    if (sourceKicker) {
        const sourceMeta = getSourcePresentation(payload.source);
        if (sourceKickerLabel) sourceKickerLabel.textContent = sourceMeta.label;
        if (sourceKickerIcon) sourceKickerIcon.innerHTML = sourceMeta.icon;
        sourceKicker.classList.toggle('hidden', !sourceMeta.label);
    }

    if (refIcon) {
        let svgContent;
        switch (payload.source) {
            case 'bible':
                svgContent = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>';
                break;
            case 'hymn':
                svgContent = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>';
                break;
            case 'sermon':
            case 'expose':
                svgContent = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>';
                break;
            default:
                svgContent = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg>';
        }
        refIcon.innerHTML = svgContent;
    }

    const hasReference = !!(payload.reference && payload.reference.trim());
    const showReference = hasReference && currentConfig.show_reference !== false;

    if (textEl) textEl.textContent = text;
    if (refEl) refEl.textContent = payload.reference || '';
    if (refBox) refBox.classList.toggle('hidden', !showReference);
    if (divider) divider.classList.toggle('hidden', !showReference);

    if (lowerThird) {
        lowerThird.classList.add('visible');
        fitTextToViewport(textEl, refEl, lowerThird.querySelector('.lt-body'), fittedBaseSize);
        if (innerWrapper) innerWrapper.classList.remove('content-hidden');
        await animateElement(innerWrapper, 'in', transition, localToken);
        if (localToken === transitionToken) resetAnimatedState(innerWrapper);
    }
}

/* ── Realtime Updates (SSE with Polling Fallback) ────────────── */
async function fetchUpdates() {
    try {
        const url = window.location.protocol === 'file:'
            ? 'http://127.0.0.1:8080/api/updates'
            : '/api/updates';
        const response = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
        if (response.ok) {
            const data = await response.json();
            if (data.config) applyConfig(data.config);
            if (data.slide) await setSlide(data.slide);
        }
    } catch (err) {
        // Silent retry
    }
}

let pollingInterval = null;

function startPolling() {
    if (pollingInterval) return;
    console.log('[OBS] Starting fallback polling...');
    fetchUpdates();
    pollingInterval = setInterval(fetchUpdates, 200);
}

function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

function startRealtimeUpdates() {
    if (window.location.protocol === 'file:') {
        startPolling();
        return;
    }

    try {
        console.log('[OBS] Connecting to SSE stream...');
        const eventSource = new EventSource('/api/stream');

        // Once the stream is (re)established, stop the polling bridge.
        eventSource.onopen = () => {
            console.log('[OBS] SSE connected.');
            stopPolling();
        };

        eventSource.onmessage = async (event) => {
            stopPolling();
            try {
                const data = JSON.parse(event.data);
                if (data.config) applyConfig(data.config);
                if (data.slide) await setSlide(data.slide);
            } catch (e) {
                console.error('[OBS] Error processing SSE update:', e);
            }
        };

        // Don't close the stream — the browser auto-reconnects EventSource.
        // Start polling only as a temporary bridge until SSE recovers.
        eventSource.onerror = () => {
            console.warn('[OBS] SSE interrupted; bridging with polling until reconnect.');
            startPolling();
        };
    } catch (e) {
        console.error('[OBS] Failed to initialize SSE. Falling back to polling.', e);
        startPolling();
    }
}

/* ── Init ────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
    if (window.initialData) {
        if (window.initialData.config) applyConfig(window.initialData.config);
        if (window.initialData.slide) {
            setSlide(window.initialData.slide).catch(() => {});
        }
    }
    // Use SSE for real-time push when served over HTTP; this automatically
    // falls back to polling on error or when opened via file://.
    startRealtimeUpdates();
});
