/* D.R.E.A.M.S — shared behaviour for every page.
   Edit NAV and CONTACTS below and every page updates (nav, footer, CTA band).
   Pages work without this file: each page ships a plain <noscript> nav, and all
   content is visible without JS (motion is CSS-only and progressive).
   <body data-page="home|boat|log|partners|team|contact"> marks the current section;
   <body data-cta="off"> hides the bottom contact band. */
(() => {
  const PLANNER = 'https://dreamsv1.kylegtran2007.workers.dev/';
  const DEMO = 'demo/v2-dashboard/';
  const CONTACTS = [
    { name: 'Kyle Tran', email: 'tran.kyl@northeastern.edu', alt: 'kylegtran2007@gmail.com', site: 'https://ka1e27.github.io/Portfolio/' },
    { name: 'Matthew Hong', email: 'hong.matt@northeastern.edu', site: 'https://matthewhong29.github.io/' }
  ];
  const NAV = [
    { id: 'boat', n: '01', label: 'The Boat', href: 'boat.html', ov: 'Everything about the boat on one page', items: [
      { href: 'boat.html#how', t: 'How a survey works', s: 'Plan, drive, sample, stream' },
      { href: 'boat.html#system', t: 'The V3 system', s: 'Annotated carrier board and specs' },
      { href: 'boat.html#model', t: 'Spin the board in 3D', s: 'Interactive model of the V3 carrier' },
      { href: 'boat.html#later', t: 'Later: arm + sediment', s: 'Where the platform is heading' }
    ]},
    { id: 'log', n: '02', label: 'Build Log', href: 'build-log.html', ov: 'Every entry, version and milestone', items: [
      { href: 'build-log.html#log', t: 'The full log', s: 'Every part we designed, built and tested' },
      { href: 'build-log.html#versions', t: 'V1 · V2 · V3', s: 'Three generations, with video' },
      { href: 'build-log.html#broke', t: 'What broke', s: 'The dead ends that shaped V3' },
      { href: 'build-log.html#roadmap', t: 'Roadmap', s: 'From V1 to sample collection' }
    ]},
    { id: 'try', n: '03', label: 'Try It', items: [
      { href: PLANNER, t: 'V1 waypoint planner', s: 'Plan a survey route on a map', ext: true },
      { href: DEMO, t: 'V2 command center', s: 'A simulated survey in your browser', ext: true }
    ]},
    { id: 'partners', n: '04', label: 'Partners', href: 'partners.html' },
    { id: 'team', n: '05', label: 'Team', href: 'team.html' }
  ];

  const page = document.body.dataset.page || '';
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const chev = '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M1.5 3.5 5 7l3.5-3.5" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>';
  const ext = (it) => it.ext ? ' target="_blank" rel="noopener"' : '';

  /* ── Nav ─────────────────────────────────────────────────────────────── */
  const header = document.getElementById('nav');
  if (header) {
    const items = NAV.map((g, i) => {
      const cur = g.id === page ? ' aria-current="page"' : '';
      if (!g.items) return `<li><a href="${g.href}"${cur}><b class="nav-n">${g.n}</b>${g.label}</a></li>`;
      return `<li class="has-dd">
        <button class="dd-btn" type="button" aria-expanded="false" aria-controls="dd-${i}"${g.id === page ? ' aria-current="true"' : ''}><span><b class="nav-n">${g.n}</b> ${g.label}</span>${chev}</button>
        <div class="dd" id="dd-${i}" hidden>${g.href ? `<a href="${g.href}"><span class="n">→</span><strong>Overview</strong><small>${g.ov}</small></a>` : ''}${g.items.map((it, k) =>
          `<a href="${it.href}"${ext(it)}><span class="n">${String(k + 1).padStart(2, '0')}</span><strong>${it.t}${it.ext ? ' ↗' : ''}</strong><small>${it.s}</small></a>`).join('')}</div>
      </li>`;
    }).join('');
    header.innerHTML = `<div class="wrap">
      <a class="brand" href="index.html" aria-label="D.R.E.A.M.S home"><img src="images/logo.svg" alt="" width="30" height="30"><span>D.R.E.A.M.S</span></a>
      <button class="burger" type="button" aria-expanded="false" aria-controls="nav-list" aria-label="Open menu"><span></span></button>
      <nav aria-label="Primary"><ul class="nav-list" id="nav-list">${items}<li class="nav-cta"><a class="btn btn-signal" href="contact.html"${page === 'contact' ? ' aria-current="page"' : ''}>Contact →</a></li></ul></nav>
    </div>`;

    const burger = header.querySelector('.burger');
    const ddButtons = [...header.querySelectorAll('.dd-btn')];
    const setDD = (btn, open) => { btn.setAttribute('aria-expanded', open); document.getElementById(btn.getAttribute('aria-controls')).hidden = !open; };
    const closeAll = (except) => ddButtons.forEach(b => b !== except && setDD(b, false));
    const setMenu = (open) => {
      header.classList.toggle('open', open);
      burger.setAttribute('aria-expanded', open);
      burger.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
      document.documentElement.style.overflow = open ? 'hidden' : '';
      if (!open) closeAll();
    };
    ddButtons.forEach(btn => {
      btn.addEventListener('click', (e) => { e.stopPropagation(); const open = btn.getAttribute('aria-expanded') !== 'true'; closeAll(btn); setDD(btn, open); });
      btn.parentElement.addEventListener('focusout', (e) => { if (!btn.parentElement.contains(e.relatedTarget) && !header.classList.contains('open')) setDD(btn, false); });
    });
    burger.addEventListener('click', () => setMenu(!header.classList.contains('open')));
    header.addEventListener('click', (e) => { if (e.target.closest('.nav-list a')) setMenu(false); });
    document.addEventListener('click', (e) => { if (!header.contains(e.target)) closeAll(); });
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      const openBtn = ddButtons.find(b => b.getAttribute('aria-expanded') === 'true');
      if (openBtn) { setDD(openBtn, false); openBtn.focus(); return; }
      if (header.classList.contains('open')) { setMenu(false); burger.focus(); }
    });
    const solid = () => header.classList.toggle('solid', window.scrollY > 24);
    solid(); window.addEventListener('scroll', solid, { passive: true });
  }

  /* ── CTA band + footer ───────────────────────────────────────────────── */
  const foot = document.getElementById('footer');
  if (foot) {
    const cta = document.body.dataset.cta === 'off' ? '' : `<section class="cta-band" aria-labelledby="cta-h"><div class="wrap">
      <div><span class="kicker">Work with us</span><h2 id="cta-h" style="margin-top:16px">Let's put it on the water together.</h2>
        <p>Funding, a mentor in the field, a fab shop or a place to test: tell us what you could bring. We read every email.</p></div>
      <div class="cta-mails">${CONTACTS.map(c => `<a href="mailto:${c.email}?subject=D.R.E.A.M.S"><div><strong>${c.name}</strong><span>${c.email}</span></div><span aria-hidden="true">→</span></a>`).join('')}</div>
    </div></section>`;
    foot.outerHTML = `${cta}<footer class="footer"><div class="wrap">
      <div class="foot-grid">
        <div class="foot-about"><a class="brand" href="index.html"><img src="images/logo.svg" alt="" width="30" height="30"><span>D.R.E.A.M.S</span></a>
          <p>Data Recovery for Environmental And Marine Surveillance. A modular autonomous survey boat, designed and built by students at Northeastern University.</p></div>
        <div><h2>Explore</h2><ul>
          <li><a href="index.html">Home</a></li><li><a href="boat.html">The Boat</a></li><li><a href="build-log.html">Build Log</a></li>
          <li><a href="partners.html">Partners</a></li><li><a href="team.html">Team</a></li><li><a href="contact.html">Contact</a></li></ul></div>
        <div><h2>Try it</h2><ul>
          <li><a href="${PLANNER}" target="_blank" rel="noopener">V1 waypoint planner ↗</a></li>
          <li><a href="${DEMO}" target="_blank" rel="noopener">V2 command center ↗</a></li>
          <li><a href="index.html#field">Field-test videos</a></li></ul></div>
        <div><h2>Contact</h2><ul>
          ${CONTACTS.map(c => `<li><a href="mailto:${c.email}">${c.name}\u00a0· ${c.email}</a></li>`).join('')}
          ${CONTACTS.map(c => `<li><a href="${c.site}" target="_blank" rel="noopener">${c.name.split(' ')[0]}'s portfolio ↗</a></li>`).join('')}</ul></div>
      </div>
      <div class="foot-base"><span>© 2026 D.R.E.A.M.S</span><a href="#main">Back to top ↑</a></div>
    </div></footer>`;
  }

  /* ── Hero video: autoplay unless reduced motion; pause control; pause offscreen ── */
  document.querySelectorAll('[data-hero-video]').forEach(video => {
    const btn = document.querySelector(`[data-toggle="${video.id}"]`);
    let userPaused = reduce;
    const label = () => { if (btn) { btn.textContent = video.paused ? '▶ Play video' : '❚❚ Pause video'; } };
    if (reduce) { video.removeAttribute('autoplay'); video.pause(); }
    video.addEventListener('play', label); video.addEventListener('pause', label);
    if (btn) btn.addEventListener('click', () => { if (video.paused) { userPaused = false; video.play(); } else { userPaused = true; video.pause(); } });
    if ('IntersectionObserver' in window) new IntersectionObserver(([en]) => {
      if (!en.isIntersecting) video.pause(); else if (!userPaused) video.play().catch(() => {});
    }).observe(video);
    label();
  });

  /* ── YouTube: swap the poster button for the player ──────────────────── */
  document.querySelectorAll('.yt[data-yt] button').forEach(btn => btn.addEventListener('click', () => {
    const box = btn.parentElement;
    const f = document.createElement('iframe');
    f.src = `https://www.youtube-nocookie.com/embed/${box.dataset.yt}?autoplay=1&rel=0&playsinline=1`;
    f.title = box.dataset.title || 'Video';
    f.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
    btn.replaceWith(f);
    f.focus();
  }));

  /* ── Build-log strip: buttons + drag to scroll ───────────────────────── */
  document.querySelectorAll('[data-strip]').forEach(strip => {
    const id = strip.id;
    const step = () => (strip.querySelector('.log-card')?.offsetWidth || 280) + 18;
    document.querySelectorAll(`[data-strip-prev="${id}"]`).forEach(b => b.addEventListener('click', () => strip.scrollBy({ left: -step() * 2, behavior: reduce ? 'auto' : 'smooth' })));
    document.querySelectorAll(`[data-strip-next="${id}"]`).forEach(b => b.addEventListener('click', () => strip.scrollBy({ left: step() * 2, behavior: reduce ? 'auto' : 'smooth' })));
    let down = false, startX = 0, startL = 0, moved = false;
    strip.addEventListener('pointerdown', (e) => { if (e.pointerType !== 'mouse') return; down = true; moved = false; startX = e.clientX; startL = strip.scrollLeft; });
    window.addEventListener('pointermove', (e) => { if (!down) return; const dx = e.clientX - startX; if (Math.abs(dx) > 4) { moved = true; strip.classList.add('dragging'); } strip.scrollLeft = startL - dx; });
    window.addEventListener('pointerup', () => { if (!down) return; down = false; setTimeout(() => strip.classList.remove('dragging'), 0); });
    strip.addEventListener('click', (e) => { if (moved) { e.preventDefault(); e.stopPropagation(); } }, true);
  });

  /* ── Board callouts: tap/click toggles the tip (hover/focus in CSS); Esc dismisses (WCAG 1.4.13) ── */
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    document.querySelectorAll('.pin button[aria-expanded="true"]').forEach(b => b.setAttribute('aria-expanded', 'false'));
    document.querySelectorAll('.pins').forEach(p => p.classList.add('tips-off'));
  });
  document.querySelectorAll('.pins').forEach(p => ['pointermove', 'focusin'].forEach(ev => p.addEventListener(ev, () => p.classList.remove('tips-off'))));
  document.querySelectorAll('.pin button').forEach(b => b.addEventListener('click', () => {
    const open = b.getAttribute('aria-expanded') !== 'true';
    document.querySelectorAll('.pin button[aria-expanded="true"]').forEach(o => o.setAttribute('aria-expanded', 'false'));
    b.setAttribute('aria-expanded', open);
  }));
  document.querySelectorAll('.board-layout').forEach(layout => {
    const pins = [...layout.querySelectorAll('.pin')], rows = [...layout.querySelectorAll('.legend li')];
    const hl = (i, on) => { if (pins[i]) pins[i].classList.toggle('hl', on); if (rows[i]) rows[i].classList.toggle('hl', on); };
    [pins, rows].forEach(list => list.forEach((el, i) => {
      el.addEventListener('pointerenter', () => hl(i, true));
      el.addEventListener('pointerleave', () => hl(i, false));
    }));
  });

  /* ── Build-log filters ───────────────────────────────────────────────── */
  const grid = document.querySelector('[data-log-grid]');
  if (grid) {
    const cards = [...grid.querySelectorAll('.log-card')];
    const count = document.querySelector('[data-log-count]');
    const state = { v: 'all', s: 'all' };
    const apply = () => {
      let n = 0;
      cards.forEach(c => { const show = (state.v === 'all' || c.dataset.v === state.v) && (state.s === 'all' || c.dataset.s === state.s); c.hidden = !show; if (show) n++; });
      if (count) count.textContent = `${n} of ${cards.length} entries`;
    };
    document.querySelectorAll('[data-filter]').forEach(btn => btn.addEventListener('click', () => {
      const [k, v] = btn.dataset.filter.split(':');
      state[k] = v;
      document.querySelectorAll(`[data-filter^="${k}:"]`).forEach(b => b.setAttribute('aria-pressed', b === btn));
      apply();
    }));
    apply();
  }

  /* ── 3D viewer: no auto-rotate for reduced motion; wider framing on phones ── */
  document.querySelectorAll('model-viewer').forEach(mv => {
    if (reduce) mv.removeAttribute('auto-rotate');
    if (window.innerWidth < 700 && mv.getAttribute('camera-orbit')) mv.setAttribute('camera-orbit', mv.getAttribute('camera-orbit').replace(/\S+%$/, '112%'));
  });

  /* ── 3D viewer camera presets ────────────────────────────────────────── */
  document.querySelectorAll('[data-orbit]').forEach(btn => btn.addEventListener('click', () => {
    const mv = document.getElementById(btn.dataset.target);
    if (!mv) return;
    mv.cameraOrbit = btn.dataset.orbit; mv.autoRotate = false;
    document.querySelectorAll(`[data-target="${btn.dataset.target}"]`).forEach(b => b.setAttribute('aria-pressed', b === btn));
  }));
})();
