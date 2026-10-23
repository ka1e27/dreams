/* D.R.E.A.M.S — shared behaviour for every page.
   Edit NAV, PROJECT and CONTACTS below and every page updates (nav, footer, CTA band).
   Pages work without this file: each page ships a plain <noscript> nav, and all
   content is visible without JS (motion is CSS-only and progressive).
   <body data-page="home|boat|log|partners|team|contact"> marks the current section;
   <body data-cta="off"> hides the bottom contact band. */
(() => {
  const PLANNER = 'https://dreamsv1.kylegtran2007.workers.dev/';
  const DEMO = 'demo/v2-dashboard/';
  const PROJECT = { name: 'D.R.E.A.M.S', email: 'DREAMSboatproject@gmail.com',     // the project's official inbox
                    instagram: 'https://www.instagram.com/dreams.boat.project/' };
  const CONTACTS = [
    { name: 'Kyle Tran', email: 'tran.kyl@northeastern.edu', site: 'https://ka1e27.github.io/Portfolio/' },
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
    { id: 'updates', n: '03', label: 'Updates', href: 'updates.html' },
    { id: 'try', n: '04', label: 'Try It', items: [
      { href: PLANNER, t: 'V1 waypoint planner', s: 'Plan a survey route on a map', ext: true },
      { href: DEMO, t: 'V2 command center', s: 'A simulated survey in your browser', ext: true }
    ]},
    { id: 'partners', n: '05', label: 'Partners', href: 'partners.html' },
    { id: 'team', n: '06', label: 'Team', href: 'team.html' }
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
      <a class="brand" href="index.html" aria-label="D.R.E.A.M.S home"><img src="img/logo.svg" alt="" width="118" height="44"></a>
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
      <div class="cta-mails">${[PROJECT, ...CONTACTS].map(c => `<a href="mailto:${c.email}?subject=D.R.E.A.M.S"><div><strong>${c.name}</strong><span>${c.email}</span></div><span aria-hidden="true">→</span></a>`).join('')}</div>
    </div></section>`;
    foot.outerHTML = `${cta}<footer class="footer"><div class="wrap">
      <div class="foot-grid">
        <div class="foot-about"><a class="brand" href="index.html"><img src="img/logo-light.svg" alt="D.R.E.A.M.S" width="129" height="48"></a>
          <p>Data Recovery for Environmental And Marine Surveillance. A modular autonomous survey boat, designed and built by students at Northeastern University.</p></div>
        <div><h2>Explore</h2><ul>
          <li><a href="index.html">Home</a></li><li><a href="boat.html">The Boat</a></li><li><a href="build-log.html">Build Log</a></li><li><a href="updates.html">Weekly updates</a></li>
          <li><a href="partners.html">Partners</a></li><li><a href="team.html">Team</a></li><li><a href="contact.html">Contact</a></li></ul></div>
        <div><h2>Try it</h2><ul>
          <li><a href="${PLANNER}" target="_blank" rel="noopener">V1 waypoint planner ↗</a></li>
          <li><a href="${DEMO}" target="_blank" rel="noopener">V2 command center ↗</a></li>
          <li><a href="index.html#field">Field-test videos</a></li></ul></div>
        <div><h2>Contact</h2><ul>
          ${[PROJECT, ...CONTACTS].map(c => `<li><a href="mailto:${c.email}">${c.name}\u00a0· ${c.email}</a></li>`).join('')}
          <li><a href="${PROJECT.instagram}" target="_blank" rel="noopener">Instagram · @dreams.boat.project ↗</a></li>
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

  /* ── Our own videos: the poster stays as a backdrop and the video plays over it ── */
  document.querySelectorAll('[data-video] > button').forEach(btn => btn.addEventListener('click', () => {
    const box = btn.parentElement;
    const v = document.createElement('video');
    v.src = box.dataset.video;
    v.controls = true;
    v.autoplay = true;
    v.playsInline = box.clientWidth >= 240;  // small tiles: phones play it full screen
    v.setAttribute('aria-label', box.dataset.title || 'Video');
    box.classList.add('playing');
    btn.tabIndex = -1;
    btn.setAttribute('aria-hidden', 'true');
    box.appendChild(v);
    const started = v.play();
    if (started) started.catch(() => {});
    v.focus();
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

  /* ── Weekly updates ───────────────────────────────────────────────────────
     UPDATES.md holds every week, newest first, under "## Week ending <Mon> <day>, <year>" (its Friday):
     one paragraph, then its photos, then everyone's bullets. The Updates page shows each week's
     paragraph and photos, and the card opens week.html?w=<YYYY-MM-DD>: the whole week, plus the longer
     write-up in updates/<YYYY-MM-DD>.md if there is one. A week comes out on its Friday at 5 pm Boston
     time; until then neither page shows it. Add ?preview to either page's URL to see it early. */
  const GH_UPD = 'https://github.com/ka1e27/dreams/blob/main/website/UPDATES.md';
  const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
  const RELEASE_HOUR = 17;            // 5 pm, Boston time, on the week's Friday
  const toSlug = (date) => {          // "Oct 16, 2026" -> "2026-10-16"
    const m = date.match(/^([a-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})$/i);
    const mo = m ? MONTHS.indexOf(m[1].toLowerCase()) : -1;
    return mo < 0 ? '' : `${m[3]}-${String(mo + 1).padStart(2, '0')}-${m[2].padStart(2, '0')}`;
  };
  const addDays = (slug, n) => { const [y, mo, d] = slug.split('-').map(Number); return new Date(Date.UTC(y, mo - 1, d + n)).toISOString().slice(0, 10); };
  const dayName = (slug, opts) => new Date(`${slug}T12:00:00Z`).toLocaleDateString('en-US', { timeZone: 'UTC', ...opts });
  const boston = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', hourCycle: 'h23' })
    .formatToParts(new Date()).map(p => [p.type, p.value]));
  const today = `${boston.year}-${boston.month}-${boston.day}`;
  const preview = new URLSearchParams(location.search).has('preview');
  const isOut = (slug) => preview || slug < today || (slug === today && +boston.hour >= RELEASE_HOUR);
  const IMG_LINE = /^\s*!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+"([^"]*)")?\s*\)\s*$/;
  const parseWeeks = (md) => md.replace(/<!--[\s\S]*?-->/g, '').replace(/^# .*$/m, '')
    .split(/^## /m).map(s => s.trim()).filter(Boolean).map(w => {
      const lines = w.split('\n'), title = lines.shift().trim();
      let m = title.match(/^week ending\s+(?:fri(?:day)?,?\s+)?(.+)$/i), slug = m ? toSlug(m[1]) : '';
      if (!slug && (m = title.match(/^week of\s+(.+)$/i)) && toSlug(m[1])) slug = addDays(toSlug(m[1]), 4);   // an old heading, dated by its Monday
      const b = lines.findIndex(l => /^\s*[-*+]\s/.test(l)), top = b < 0 ? lines : lines.slice(0, b);
      return {
        title, slug,
        para: top.filter(l => !IMG_LINE.test(l)).join('\n').trim(),
        pics: top.map(l => l.match(IMG_LINE)).filter(Boolean).map(([, alt, src, cap]) => ({ alt, src, cap: cap || alt })),
        bullets: b < 0 ? '' : lines.slice(b).join('\n').trim(),
      };
    }).filter(w => !w.slug || isOut(w.slug));
  const weekHref = (slug) => `week.html?w=${slug}${preview ? '&preview' : ''}`;
  const getText = (url) => fetch(url, { cache: 'no-cache' }).then(r => (r.ok ? r.text() : null)).catch(() => null);
  const writeUp = (slug) => getText(`updates/${slug}.md`);
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  // Photos made by tools/build_images.py come as img/<slug>-1600.jpg plus -900 and .webp copies; anything else is used as is.
  const built = (src) => /^img\/[\w-]+-1600\.jpg$/.test(src);
  const photo = (src, sizes, loading = 'lazy') => {
    if (!built(src)) return `<img src="${esc(src)}" alt="" loading="${loading}" decoding="async">`;
    const b = src.slice(0, -'-1600.jpg'.length);
    return `<picture><source type="image/webp" srcset="${b}-900.webp 900w, ${b}-1600.webp 1600w" sizes="${sizes}">` +
      `<img src="${b}-900.jpg" srcset="${b}-900.jpg 900w, ${b}-1600.jpg 1600w" sizes="${sizes}" alt="" loading="${loading}" decoding="async"></picture>`;
  };

  const fits = (src) => /\.(png|svg)$/i.test(src);       // renders and logos are shown whole, not cropped
  const thumbs = (pics) => `<div class="week-pics" aria-hidden="true">${pics.slice(0, 3).map(p =>
    `<div class="wk-pic${fits(p.src) ? ' fit' : ''}">${photo(p.src, '(max-width: 680px) 30vw, 230px')}</div>`).join('')}</div>`;

  const upd = document.querySelector('[data-updates]');
  if (upd) {
    const fail = () => { upd.innerHTML = `<p class="lead">The updates didn't load. Read them <a href="${GH_UPD}">on GitHub</a>.</p>`; };
    getText(upd.dataset.src).then(md => {
      if (md == null || !window.marked) return fail();
      const weeks = parseWeeks(md);
      if (!weeks.length) { upd.innerHTML = '<p class="lead">The first weekly update comes out on Friday.</p>'; return; }
      upd.innerHTML = weeks.map(w => {
        const date = w.slug ? `<span class="label">Week ending</span><h2>${dayName(w.slug, { month: 'short', day: 'numeric', year: 'numeric' })}</h2>` : `<h2>${esc(w.title)}</h2>`;
        const more = w.slug ? `<a class="week-more" href="${weekHref(w.slug)}">See the full week →</a>` : '';
        // the paragraph and its photos; a week with no paragraph yet shows its bullets instead
        return `<article class="week reveal${more ? ' has-more' : ''}"${w.slug ? ` data-slug="${w.slug}"` : ''}><div class="week-date">${date}</div>` +
          `<div class="week-body">${window.marked.parse(w.para || w.bullets)}${w.pics.length ? thumbs(w.pics) : ''}${more}</div></article>`;
      }).join('');
      // a week with no photos of its own borrows its write-up's
      weeks.filter(w => w.slug && !w.pics.length).forEach(w => writeUp(w.slug).then(full => {
        const pics = full ? [...full.matchAll(/!\[[^\]]*\]\(\s*([^)\s]+)/g)].map(m => ({ src: m[1] })) : [];
        const more = upd.querySelector(`.week[data-slug="${w.slug}"] .week-more`);
        if (pics.length && more) more.insertAdjacentHTML('beforebegin', thumbs(pics));
      }));
    });
  }

  /* Home page: the newest week that's out, as one card (its paragraph as plain text and its first photo).
     It follows the same Friday 5 pm release as the Updates page, and stays hidden if nothing loads. */
  const latest = document.querySelector('[data-latest]');
  if (latest) {
    getText(latest.dataset.src).then(md => {
      const w = md ? parseWeeks(md).find(x => x.slug && x.para) : null;
      if (!w) return;
      const plain = (s) => s.replace(/!\[[^\]]*\]\([^)]*\)/g, '').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
        .replace(/[*_`]+/g, '').replace(/\s+/g, ' ').trim();
      latest.querySelector('[data-latest-date]').textContent = `Week ending ${dayName(w.slug, { month: 'short', day: 'numeric', year: 'numeric' })}`;
      latest.querySelector('[data-latest-para]').textContent = plain(w.para);
      latest.querySelector('[data-latest-link]').href = weekHref(w.slug);
      const box = latest.querySelector('[data-latest-pic]'), pic = w.pics[0];
      if (pic) { box.innerHTML = photo(pic.src, '(max-width: 680px) 90vw, 320px'); box.classList.toggle('fit', fits(pic.src)); }
      else box.remove();
      latest.hidden = false;
    });
  }

  /* Full-size photo viewer for a week's gallery (Esc closes, arrow keys step through) */
  const lightbox = (buttons) => {
    if (!buttons.length) return;
    const dlg = document.createElement('dialog');
    dlg.className = 'lightbox';
    dlg.setAttribute('aria-label', 'Photo');
    const many = buttons.length > 1;
    dlg.innerHTML = `<figure><figcaption></figcaption></figure><span class="lb-count" aria-live="polite"></span>
      <button type="button" class="lb-btn lb-close" aria-label="Close photo">×</button>${many ? `<button type="button" class="lb-btn lb-prev" aria-label="Previous photo">‹</button><button type="button" class="lb-btn lb-next" aria-label="Next photo">›</button>` : ''}`;
    document.body.appendChild(dlg);
    const fig = dlg.querySelector('figure'), cap = dlg.querySelector('figcaption'), count = dlg.querySelector('.lb-count');
    const img = document.createElement('img');      // added on first open, once it has a src
    let at = 0;
    const show = (i) => {
      at = (i + buttons.length) % buttons.length;
      const b = buttons[at];
      img.src = b.dataset.full; img.alt = b.dataset.alt; cap.textContent = b.dataset.cap;
      if (!img.isConnected) fig.prepend(img);
      count.textContent = many ? `${at + 1} / ${buttons.length}` : '';
    };
    buttons.forEach((b, i) => b.addEventListener('click', () => { show(i); dlg.showModal(); }));
    dlg.addEventListener('click', (e) => { if (e.target === dlg || e.target.tagName === 'FIGURE') dlg.close(); });
    dlg.querySelector('.lb-close').addEventListener('click', () => dlg.close());
    if (many) {
      dlg.querySelector('.lb-prev').addEventListener('click', () => show(at - 1));
      dlg.querySelector('.lb-next').addEventListener('click', () => show(at + 1));
      dlg.addEventListener('keydown', (e) => { if (e.key === 'ArrowLeft') show(at - 1); else if (e.key === 'ArrowRight') show(at + 1); });
    }
  };

  /* week.html?w=YYYY-MM-DD (the week's Friday) */
  const wk = document.querySelector('[data-week]');
  if (wk) {
    let slug = new URLSearchParams(location.search).get('w') || '';
    const valid = /^\d{4}-\d{2}-\d{2}$/.test(slug);
    if (valid && new Date(`${slug}T12:00:00Z`).getUTCDay() === 1) slug = addDays(slug, 4);   // older links used the week's Monday
    const head = document.querySelector('[data-week-head]');
    const missing = (msg) => { wk.innerHTML = `<p class="lead">${msg} See <a href="updates.html">all the weekly updates</a>.</p>`; };
    Promise.all([getText('UPDATES.md'), valid && isOut(slug) ? writeUp(slug) : Promise.resolve(null)]).then(([md, full]) => {
      if (!window.marked) return missing("This week didn't load.");
      if (valid && !isOut(slug)) return missing(`This week's update comes out on ${dayName(slug, { weekday: 'long', month: 'long', day: 'numeric' })}.`);
      const weeks = md ? parseWeeks(md).filter(w => w.slug) : [];
      const i = weeks.findIndex(w => w.slug === slug);
      const week = weeks[i];
      if (!week && !full) return missing("We couldn't find that week.");
      const label = `Week ending ${dayName(slug, { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' })}`;
      document.title = `${label} — D.R.E.A.M.S`;
      head.querySelector('[data-wk-kicker]').textContent = label;

      // the write-up, if there is one: "# Headline", then sections; image-only paragraphs become galleries
      const body = document.createElement('div');
      body.innerHTML = full ? window.marked.parse(full) : '';
      const h1 = body.querySelector('h1');
      head.querySelector('[data-wk-title]').textContent = h1 ? h1.textContent : `The week ending ${dayName(slug, { month: 'long', day: 'numeric' })}`;
      if (h1) h1.remove();
      // the lead is the week's paragraph; an older write-up's own opening paragraph gives way to it
      const intro = body.firstElementChild, introText = intro && intro.tagName === 'P' && !intro.querySelector('img');
      const lead = head.querySelector('[data-wk-lead]');
      if (week && week.para) { lead.innerHTML = window.marked.parseInline(week.para); lead.hidden = false; if (introText) intro.remove(); }
      else if (introText) { lead.innerHTML = intro.innerHTML; lead.hidden = false; intro.remove(); }

      const figure = (p, one) => `<figure><button type="button" class="ph" data-full="${esc(p.src)}" data-alt="${esc(p.alt)}" data-cap="${esc(p.cap)}" aria-label="Open photo: ${esc(p.alt || 'photo')}">` +
        `${photo(p.src, one ? '(max-width: 900px) 100vw, 860px' : '(max-width: 680px) 100vw, 430px')}</button>${p.cap ? `<figcaption>${esc(p.cap)}</figcaption>` : ''}</figure>`;
      const gallery = (pics) => `<div class="gallery${pics.length === 1 ? ' one' : ''}">${pics.map(p => figure(p, pics.length === 1)).join('')}</div>`;
      const shown = new Set((week ? week.pics : []).map(p => p.src));     // a photo the week already shows isn't repeated below
      body.querySelectorAll('p').forEach(p => {
        const imgs = [...p.querySelectorAll('img')];
        if (!imgs.length || p.textContent.trim()) return;
        const pics = imgs.map(im => ({ src: im.getAttribute('src'), alt: im.getAttribute('alt') || '', cap: im.getAttribute('title') || im.getAttribute('alt') || '' })).filter(x => !shown.has(x.src));
        if (!pics.length) return p.remove();
        const g = document.createElement('div');
        g.innerHTML = gallery(pics);
        p.replaceWith(g.firstElementChild);
      });

      // the week's photos, what each of us did, then the write-up
      const bullets = week && week.bullets ? `<section class="wk-short"><span class="label">What each of us did</span><div class="week-body">${window.marked.parse(week.bullets)}</div></section>` : '';
      wk.innerHTML = `${week && week.pics.length ? gallery(week.pics) : ''}${bullets}<article class="wk-body">${body.innerHTML}</article><nav class="wk-nav" aria-label="Other weeks"></nav>`;

      // the first photo moves into the page head's blob (it still opens full size, first in the viewer)
      const first = wk.querySelector('.gallery figure');
      let cover = null;
      if (first) {
        const b = first.querySelector('.ph'), g = first.parentElement;
        first.remove();
        if (!g.children.length) g.remove(); else if (g.children.length === 1) g.classList.add('one');
        const bg = head.querySelector('.bg');
        bg.innerHTML = `<button type="button" class="ph-head" aria-label="${esc(b.getAttribute('aria-label'))}"><img src="${esc(b.dataset.full)}" alt=""></button>`;
        cover = bg.querySelector('.ph-head');
        Object.assign(cover.dataset, b.dataset);
        const hi = cover.querySelector('img');
        const show = () => { if (hi.naturalWidth) head.style.setProperty('--ar', (hi.naturalWidth / hi.naturalHeight).toFixed(3)); bg.hidden = false; };
        if (hi.complete) show(); else hi.addEventListener('load', show, { once: true });
      }
      lightbox([...(cover ? [cover] : []), ...wk.querySelectorAll('.gallery .ph')]);
      // each photo sizes its slot from its own proportions, so a row of mixed photos lines up without cropping
      wk.querySelectorAll('.gallery img').forEach(im => {
        const fit = () => { if (im.naturalWidth) im.closest('figure').style.setProperty('--ar', (im.naturalWidth / im.naturalHeight).toFixed(3)); };
        if (im.complete) fit(); else im.addEventListener('load', fit, { once: true });
      });

      // the older and newer weeks that are out
      const link = (w, rel) => w ? `<a class="wk-${rel}" href="${weekHref(w.slug)}"><span class="label">${rel === 'older' ? '← Older' : 'Newer →'}</span><strong>Week ending ${dayName(w.slug, { month: 'short', day: 'numeric' })}</strong></a>` : '<span></span>';
      wk.querySelector('.wk-nav').innerHTML = `${link(i >= 0 ? weeks[i + 1] : null, 'older')}<a class="wk-all btn btn-ghost" href="updates.html">All updates</a>${link(i > 0 ? weeks[i - 1] : null, 'newer')}`;
    });
  }

  /* ── Build-log filters ───────────────────────────────────────────────── */
  const grid = document.querySelector('[data-log-grid]');
  if (grid) {
    const cards = [...grid.querySelectorAll('.log-card')];
    const count = document.querySelector('[data-log-count]');
    const more = document.querySelector('[data-log-more]');
    const LIMIT = 10;  // the rest open with "Show all"
    const state = { v: 'all', s: 'all', all: false };
    const apply = () => {
      let n = 0;
      cards.forEach(c => { const match = (state.v === 'all' || c.dataset.v === state.v) && (state.s === 'all' || c.dataset.s === state.s); c.hidden = !match || (!state.all && n >= LIMIT); if (match) n++; });
      if (count) count.textContent = `${n} of ${cards.length} entries`;
      if (more) { more.hidden = n <= LIMIT; more.textContent = state.all ? 'Show fewer' : `Show all ${n} entries`; more.setAttribute('aria-expanded', state.all); }
    };
    if (more) more.addEventListener('click', () => { state.all = !state.all; apply(); if (!state.all) grid.scrollIntoView({ block: 'start' }); });
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
