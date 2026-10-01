/*
 * Scenes: pure functions of t. Replace these with your script.
 *
 * Timing comes from the music's bar grid (TIMING.bpm, beats per bar) so every
 * cut lands on a bar. Put VO word times from `cli.py whisper` or `cli.py voice`
 * into CUES and key on-screen words to them instead of guessing.
 */
(function (root) {
	'use strict';
	const { C, E, F, clamp, lerp, seg, win, text, fit, typed, scramble, slam, corners, tag, flash, safe } = root.FF;

	const TIMING = { bpm: 120, beatsPerBar: 4, offset: 0 };
	const BAR = (60 / TIMING.bpm) * TIMING.beatsPerBar; // 2 s at 120 bpm
	const bar = (n) => TIMING.offset + n * BAR;

	// Example cue sheet (seconds). Fill from word timings, not by eye.
	const CUES = { open: bar(0), idea: bar(1), hold: bar(2), end: bar(3) };

	function bg(ctx) {
		ctx.fillStyle = C.bg;
		ctx.fillRect(0, 0, root.FF.W, root.FF.H);
	}

	// Scene 1: a mono "machine voice" prompt with a typing cursor.
	function sPrompt(ctx, t) {
		const W = root.FF.W;
		const H = root.FF.H;
		const s = safe();
		const a = win(t, CUES.open, CUES.idea, 0.2, 0.15);
		if (a <= 0) return;
		root.FF.setGA(a);
		const px = H > W ? 52 : 44;
		const line = '> one idea per line';
		const shown = typed(line, CUES.open + 0.2, t, 22);
		const x = s.left + 40;
		const y = H * 0.5;
		text(ctx, shown + (Math.floor(t * 2) % 2 ? '_' : ' '), x, y, F(500, px, 'mono'), C.ink);
		text(ctx, 'SCENE 01 · 00:00', x, y - px * 1.6, F(400, Math.round(px * 0.55), 'mono'), C.mid, 'left', 1, 2);
		corners(ctx, s.left, y - px * 3, s.right - s.left, px * 4.6, 30, C.acc, 0.8);
		root.FF.setGA(1);
	}

	// Scene 2: the hero line slams in on the bar, with an eased accent flash.
	function sIdea(ctx, t) {
		const W = root.FF.W;
		const H = root.FF.H;
		const s = safe();
		const a = win(t, CUES.idea, CUES.hold, 0, 0.2);
		if (a <= 0) return;
		root.FF.setGA(a);
		const word = 'ONE IDEA.';
		const px = fit(ctx, word, 800, 'head', s.right - s.left, H > W ? 260 : 300);
		slam(ctx, word, W / 2, H * 0.5 + px * 0.33, F(800, px, 'head'), C.ink, CUES.idea, t);
		tag(ctx, 'LINE 01', W / 2, H * 0.5 - px * 0.75, F(700, 34, 'mono'), { align: 'center', alpha: clamp((t - CUES.idea - 0.25) / 0.2), track: 3 });
		root.FF.setGA(1);
	}

	// Scene 3: scramble-lock headline plus a serif line for the emotional beat. Long hold.
	function sHold(ctx, t) {
		const W = root.FF.W;
		const H = root.FF.H;
		const s = safe();
		const a = win(t, CUES.hold, CUES.end, 0, 0.25);
		if (a <= 0) return;
		root.FF.setGA(a);
		// Phone layouts stack; they are designed vertical, not cropped from 16:9.
		const lines = H > W ? ['HELD LONG', 'ENOUGH'] : ['HELD LONG ENOUGH'];
		const px = Math.min(...lines.map((l) => fit(ctx, l, 800, 'head', s.right - s.left, 220)));
		lines.forEach((l, i) => {
			const y = H * 0.47 - (lines.length - 1 - i) * px * 0.95;
			text(ctx, scramble(l, CUES.hold + i * 0.12, t, 0.5, i), W / 2, y, F(800, px, 'head'), C.acc, 'center');
		});
		const sp = Math.max(H > W ? 64 : 48, Math.round(px * 0.42));
		text(ctx, 'to actually read it.', W / 2, H * 0.47 + sp * 1.7, `italic 400 ${sp}px ${root.FF.FAM.serif}`, C.ink, 'center', E.outCubic(seg(t, CUES.hold + 0.4, CUES.hold + 0.9)));
		root.FF.setGA(1);
	}

	// Scene 4: end on an idea, not a logo slate. Tiny sign-off only.
	function sEnd(ctx, t) {
		const W = root.FF.W;
		const H = root.FF.H;
		const s = safe();
		const a = win(t, CUES.end, reel.DURATION + 1, 0.4, 0);
		if (a <= 0) return;
		root.FF.setGA(a);
		const px = H > W ? 96 : 110;
		const rise = lerp(24, 0, E.outCubic(seg(t, CUES.end, CUES.end + 0.8)));
		text(ctx, 'Cut on the beat.', W / 2, H * 0.5 + rise, `italic 500 ${px}px ${root.FF.FAM.serif}`, C.ink, 'center');
		text(ctx, 'made with video-reels', W / 2, s.bottom - 10, F(400, 26, 'mono'), C.dim, 'center', 1, 2);
		root.FF.setGA(1);
	}

	const reel = {
		DURATION: bar(4),
		TIMING,
		CUES,
		FAST: [[CUES.idea - 0.05, CUES.idea + 0.3]],
		load: async () => true,
		composite(ctx, t) {
			bg(ctx);
			sPrompt(ctx, t);
			sIdea(ctx, t);
			sHold(ctx, t);
			sEnd(ctx, t);
			flash(ctx, t, CUES.idea, 0.2, C.acc, 0.55);
		},
	};
	root.FF_REEL = reel;
})(typeof window !== 'undefined' ? window : globalThis);
