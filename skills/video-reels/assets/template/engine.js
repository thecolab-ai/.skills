/*
 * Reel engine: a tiny 2D-canvas motion engine for kinetic-type videos.
 *
 * Contract: every frame is a pure function of time. `composite(ctx, t)` paints
 * the whole frame from nothing, so the live preview and the frame-exact export
 * share one code path and any frame can be rendered in any order, on any page.
 *
 * Coordinates are logical pixels (FF.W × FF.H). The canvas may be smaller or
 * larger (`?scale=`); the engine sets the transform for you.
 */
(function (root) {
	'use strict';

	const ASPECTS = {
		'9x16': [1080, 1920],
		'16x9': [1920, 1080],
		'1x1': [1080, 1080],
		'4x5': [1080, 1350],
	};
	let W = 1080;
	let H = 1920;
	const TAU = Math.PI * 2;

	// One accent colour plus near-black and off-white. Swap `acc` per project; keep the rest.
	const C = {
		bg: '#060606',
		deep: '#0E0E0D',
		ink: '#F2EEE8',
		acc: '#FF6A2B',
		onAcc: '#140502',
		mid: '#9A9A92',
		dim: '#5C5C57',
		faint: '#1F1F1D',
		stroke: '#3A3A36',
	};

	/* ── Math ──────────────────────────────────────────────── */
	const clamp = (v, a = 0, b = 1) => (v < a ? a : v > b ? b : v);
	const lerp = (a, b, p) => a + (b - a) * p;
	const seg = (t, a, b) => clamp((t - a) / (b - a));
	const frac = (x) => x - Math.floor(x);
	// Deterministic hash: never use Math.random() in a scene.
	const hash = (n) => frac(Math.sin(n * 91.345 + 47.853) * 43758.5453);
	function noise(x, seed = 0) {
		const i = Math.floor(x);
		const f = x - i;
		const u = f * f * (3 - 2 * f);
		return lerp(hash(i + seed * 17.1), hash(i + 1 + seed * 17.1), u);
	}
	const E = {
		lin: (p) => p,
		outCubic: (p) => 1 - Math.pow(1 - p, 3),
		inCubic: (p) => p * p * p,
		inOutCubic: (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2),
		outExpo: (p) => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)),
		inExpo: (p) => (p <= 0 ? 0 : Math.pow(2, 10 * p - 10)),
		outQuint: (p) => 1 - Math.pow(1 - p, 5),
		outBack: (p) => 1 + 2.9 * Math.pow(p - 1, 3) + 1.9 * Math.pow(p - 1, 2),
	};
	// Visibility window: fade in over fin after a, fade out over fout before b.
	const win = (t, a, b, fin = 0.3, fout = 0.3) =>
		Math.min(fin > 0 ? E.outCubic(seg(t, a, a + fin)) : t >= a ? 1 : 0, fout > 0 ? 1 - E.inCubic(seg(t, b - fout, b)) : t < b ? 1 : 0);

	const rgbCache = {};
	function rgb(hex) {
		if (!rgbCache[hex]) {
			const n = parseInt(hex.slice(1), 16);
			rgbCache[hex] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
		}
		return rgbCache[hex];
	}
	const rgba = (hex, a) => {
		const [r, g, b] = rgb(hex);
		return `rgba(${r},${g},${b},${a})`;
	};

	/* ── Type: three families, three fixed jobs ────────────── */
	// head = impact grotesk, mono = machine voice, serif = emotion.
	// Self-host the real fonts in index.html with font-display:block; these stacks are fallbacks.
	const FAM = {
		head: `'Barlow Condensed', 'Arial Narrow', 'Liberation Sans Narrow', sans-serif`,
		mono: `'JetBrains Mono', 'DejaVu Sans Mono', ui-monospace, monospace`,
		serif: `'EB Garamond', Georgia, 'DejaVu Serif', serif`,
		sans: `'Inter', 'Helvetica Neue', Arial, sans-serif`,
	};
	const F = (w, px, fam = 'sans') => `${w} ${px}px ${FAM[fam]}`;
	const pxOf = (font) => parseFloat(font.match(/(\d+(?:\.\d+)?)px/)[1]);

	const ready = (async () => {
		if (typeof document === 'undefined' || !document.fonts) return;
		const specs = [F(400, 40, 'mono'), F(700, 40, 'mono'), 'italic 400 40px ' + FAM.serif, F(800, 40, 'head'), F(600, 40, 'head'), F(500, 40, 'sans')];
		await Promise.all(specs.map((s) => document.fonts.load(s, 'AZaz 0123').catch(() => {})));
		await document.fonts.ready;
	})();

	/* ── Scene alpha (multiplies every draw call) ──────────── */
	let GA = 1;

	/* ── Drawing helpers ───────────────────────────────────── */
	function rr(ctx, x, y, w, h, r) {
		r = Math.min(r, w / 2, h / 2);
		ctx.beginPath();
		ctx.moveTo(x + r, y);
		ctx.arcTo(x + w, y, x + w, y + h, r);
		ctx.arcTo(x + w, y + h, x, y + h, r);
		ctx.arcTo(x, y + h, x, y, r);
		ctx.arcTo(x, y, x + w, y, r);
		ctx.closePath();
	}
	function setFont(ctx, font, track = 0) {
		ctx.font = font;
		ctx.letterSpacing = `${track}px`;
	}
	function measure(ctx, s, font, track = 0) {
		setFont(ctx, font, track);
		return ctx.measureText(s).width - (s.length ? track : 0);
	}
	function text(ctx, s, x, y, font, color, align = 'left', alpha = 1, track = 0) {
		const w = measure(ctx, s, font, track);
		const x0 = align === 'center' ? x - w / 2 : align === 'right' ? x - w : x;
		if (alpha * GA <= 0.001) return { w, x0 };
		ctx.globalAlpha = clamp(alpha * GA);
		ctx.fillStyle = color;
		ctx.textAlign = 'left';
		ctx.fillText(s, x0, y);
		ctx.globalAlpha = 1;
		return { w, x0 };
	}
	// Biggest px (≤ maxPx) at which s fits maxW.
	function fit(ctx, s, weight, fam, maxW, maxPx, track = 0) {
		const w = measure(ctx, s, F(weight, 100, fam), track);
		return Math.min(maxPx, Math.floor((100 * maxW) / Math.max(1, w)));
	}
	function wrap(ctx, s, font, maxW, track = 0) {
		const lines = [];
		let cur = '';
		for (const w of s.split(' ')) {
			const next = cur ? cur + ' ' + w : w;
			if (cur && measure(ctx, next, font, track) > maxW) {
				lines.push(cur);
				cur = w;
			} else cur = next;
		}
		if (cur) lines.push(cur);
		return lines;
	}
	// Typewriter: characters revealed at cps from t0.
	const typed = (s, t0, t, cps = 28) => Array.from(s).slice(0, Math.floor(clamp((t - t0) * cps, 0, s.length))).join('');
	// Scramble: glyphs flicker then lock left-to-right between t0 and t0 + dur.
	const GLYPHS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&*+=/<>';
	function scramble(s, t0, t, dur = 0.6, seed = 0) {
		if (t < t0) return '';
		const ch = Array.from(s);
		const p = clamp((t - t0) / dur);
		const tick = Math.floor(t * 30);
		return ch
			.map((c, i) => {
				const lock = (i + 1) / ch.length;
				if (p >= lock || c === ' ') return c;
				if (p < lock - 0.5) return i / ch.length < p * 2 ? GLYPHS[Math.floor(hash(i * 7 + tick + seed) * GLYPHS.length)] : ' ';
				return GLYPHS[Math.floor(hash(i * 13 + tick * 3 + seed) * GLYPHS.length)];
			})
			.join('');
	}
	// Slam: text scales down from `from` onto its spot.
	function slam(ctx, s, x, y, font, color, t0, t, o = {}) {
		const d = t - t0;
		if (d < 0) return;
		const sc = lerp(o.from ?? 1.8, 1, E.outExpo(clamp(d / (o.dur ?? 0.35))));
		ctx.save();
		ctx.translate(x, y);
		ctx.scale(sc, sc);
		text(ctx, s, 0, 0, font, color, o.align || 'center', clamp(d / 0.06) * (o.alpha ?? 1), o.track || 0);
		ctx.restore();
	}

	/* ── HUD texture ───────────────────────────────────────── */
	function corners(ctx, x, y, w, h, len = 28, color = C.acc, alpha = 1, lw = 3) {
		ctx.globalAlpha = alpha * GA;
		ctx.strokeStyle = color;
		ctx.lineWidth = lw;
		ctx.beginPath();
		for (const [cx, cy, sx, sy] of [
			[x, y, 1, 1],
			[x + w, y, -1, 1],
			[x, y + h, 1, -1],
			[x + w, y + h, -1, -1],
		]) {
			ctx.moveTo(cx, cy + sy * len);
			ctx.lineTo(cx, cy);
			ctx.lineTo(cx + sx * len, cy);
		}
		ctx.stroke();
		ctx.globalAlpha = 1;
	}
	function tag(ctx, s, x, y, font, o = {}) {
		const w = measure(ctx, s, font, o.track || 0);
		const px = pxOf(font);
		const padX = o.padX ?? px * 0.45;
		const h = px * 1.45;
		const x0 = o.align === 'center' ? x - w / 2 - padX : o.align === 'right' ? x - w - 2 * padX : x;
		ctx.globalAlpha = (o.alpha ?? 1) * GA;
		ctx.fillStyle = o.bg || C.acc;
		ctx.fillRect(x0, y - h * 0.74, w + padX * 2, h);
		ctx.globalAlpha = 1;
		text(ctx, s, x0 + padX, y, font, o.color || C.onAcc, 'left', o.alpha ?? 1, o.track || 0);
		return w + padX * 2;
	}
	// Accent flash that PEAKS on t0. Eased in over ~3 frames: a hard 1-frame onset reads as flicker.
	function flash(ctx, t, t0, dur = 0.18, color = C.acc, peak = 0.9) {
		const att = 0.1;
		const d = t - t0;
		if (d < -att || d > dur) return;
		const s = (x) => x * x * (3 - 2 * x);
		ctx.globalAlpha = peak * (d < 0 ? s(1 + d / att) : 1 - s(d / dur)) * GA;
		ctx.fillStyle = color;
		ctx.fillRect(0, 0, W, H);
		ctx.globalAlpha = 1;
	}
	// Vertical safe area: platform UI covers the top and bottom of phone video.
	function safe() {
		const v = H > W;
		return { top: v ? 220 : 80, bottom: v ? H - 300 : H - 90, left: v ? 72 : 120, right: v ? W - 72 : W - 120 };
	}

	/* ── Grain / vignette ──────────────────────────────────── */
	let grainPat = null;
	function grain(ctx, t, amt) {
		if (!grainPat) {
			const c = document.createElement('canvas');
			c.width = c.height = 256;
			const g = c.getContext('2d');
			const im = g.createImageData(256, 256);
			for (let i = 0; i < im.data.length; i += 4) {
				const v = Math.floor(hash(i * 0.37 + 11) * 255);
				im.data[i] = im.data[i + 1] = im.data[i + 2] = v;
				im.data[i + 3] = 255;
			}
			g.putImageData(im, 0, 0);
			grainPat = ctx.createPattern(c, 'repeat');
		}
		const f = Math.floor(t * 24);
		const ox = Math.floor(hash(f) * 256);
		const oy = Math.floor(hash(f + 3.3) * 256);
		ctx.save();
		ctx.globalCompositeOperation = 'overlay';
		ctx.globalAlpha = amt;
		ctx.translate(ox, oy);
		ctx.fillStyle = grainPat;
		ctx.fillRect(-ox, -oy, W, H);
		ctx.restore();
	}
	function overlays(ctx, t, reel, state) {
		ctx.globalCompositeOperation = 'source-over';
		ctx.setTransform(ctx.canvas.width / W, 0, 0, ctx.canvas.height / H, 0, 0);
		const r = Math.max(W, H);
		const vig = ctx.createRadialGradient(W / 2, H / 2, r * 0.27, W / 2, H / 2, r * 0.65);
		vig.addColorStop(0, 'rgba(0,0,0,0)');
		vig.addColorStop(1, 'rgba(0,0,0,0.7)');
		ctx.globalAlpha = reel.vig ? reel.vig(t) : 1;
		ctx.fillStyle = vig;
		ctx.fillRect(0, 0, W, H);
		ctx.globalAlpha = 1;
		if (state.grain > 0) grain(ctx, t, state.grain);
	}

	/* ── Renderer ──────────────────────────────────────────── */
	function drawScene(ctx, t, reel) {
		GA = 1;
		ctx.globalAlpha = 1;
		ctx.globalCompositeOperation = 'source-over';
		ctx.textBaseline = 'alphabetic';
		ctx.textAlign = 'left';
		ctx.setLineDash([]);
		ctx.letterSpacing = '0px';
		ctx.shadowBlur = 0;
		ctx.filter = 'none';
		ctx.save();
		reel.composite(ctx, t);
		ctx.restore();
	}
	// samples > 1 = motion blur (temporal supersampling inside a shutter of shutter/fps).
	// reel.FAST lists [a, b] spans that use fastSamples instead (whip pans, slams).
	function create(canvas, reel, opts = {}) {
		const ctx = canvas.getContext('2d', { alpha: false });
		let layer = null;
		let lctx = null;
		const state = {
			samples: opts.samples || 1,
			fastSamples: opts.fastSamples || opts.samples || 1,
			shutter: opts.shutter ?? 0.5,
			fps: opts.fps || 30,
			grain: opts.grain ?? 0.05,
		};
		const base = (c) => c.setTransform(canvas.width / W, 0, 0, canvas.height / H, 0, 0);
		const isFast = (t) => (reel.FAST || []).some(([a, b]) => t >= a && t <= b);
		function render(t) {
			const D = reel.DURATION;
			t = clamp(t, 0, D);
			const n = isFast(t) ? state.fastSamples : state.samples;
			if (n <= 1) {
				base(ctx);
				drawScene(ctx, t, reel);
			} else {
				if (!layer || layer.width !== canvas.width || layer.height !== canvas.height) {
					layer = document.createElement('canvas');
					layer.width = canvas.width;
					layer.height = canvas.height;
					lctx = layer.getContext('2d', { alpha: false });
				}
				const span = state.shutter / state.fps;
				for (let s = 0; s < n; s++) {
					const ts = clamp(t + ((s + 0.5) / n - 0.5) * span, 0, D);
					base(lctx);
					drawScene(lctx, ts, reel);
					ctx.setTransform(1, 0, 0, 1, 0, 0);
					ctx.globalAlpha = 1 / (s + 1);
					ctx.drawImage(layer, 0, 0);
				}
				ctx.globalAlpha = 1;
			}
			overlays(ctx, t, reel, state);
		}
		return { render, state };
	}
	function setAspect(name) {
		const size = ASPECTS[name] || ASPECTS['9x16'];
		W = size[0];
		H = size[1];
		return { W, H };
	}

	root.FF = {
		ASPECTS, TAU, C, E, FAM,
		get W() { return W; },
		get H() { return H; },
		get GA() { return GA; },
		setGA(a) { GA = a; },
		setAspect,
		clamp, lerp, seg, frac, hash, noise, win, rgb, rgba, F, pxOf,
		rr, setFont, measure, text, fit, wrap, typed, scramble, slam, corners, tag, flash, safe,
		ready, create,
	};
})(typeof window !== 'undefined' ? window : globalThis);
