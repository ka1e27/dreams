/* Boat page: the V3 boat in 3D (section #explore).
   media/boat-v3.glb is exported from our SolidWorks model through its API: six parts, colours from the CAD,
   metres, Y up. Spin it, pull it apart, slice it bow to stern or port to starboard, and read why each part
   is built the way it is. three.js (pinned by the import map in boat.html) loads only when the section
   comes near the screen. */

/* ---------- content ---------- */
const SWATCH = { hull: '#C00000', deck: '#F2F4F5', bridge: '#FFC0C0', name: '#E4E4E4' };
const GROUPS = [
  { name: 'Hulls', ids: ['hull-port', 'hull-stbd'] },
  { name: 'Deck plates', ids: ['deck-port', 'deck-stbd'] },
  { name: 'Bridge', ids: ['bridge'] },
  { name: 'Name', ids: ['name'] },
];
const HULL = {
  why: [
    'Two hulls instead of one. A catamaran sits level and is hard to tip over, which keeps the sensors steady while the boat samples.',
    'Printed in one piece, standing on end. The large-format printer we use builds up to 1000 mm tall, so the 940 mm hull fits with 60 mm to spare, and there are no joints along the hull to seal.',
    '220 mm wide. In our sizing model, narrower hulls sat too low in the water once the batteries and electronics were aboard.',
    'Hollow, with 6 mm walls, so the batteries and electronics can ride inside, low down where their weight steadies the boat.',
    'A deep V bottom, about 26°, and a keel that sweeps up at the bow, to help it hold a straight line and ride over small waves.',
  ],
  history: [
    ['V1', 'PLA hulls, printed in sections and brushed with marine epoxy.'],
    ['V2', 'Printed in sections, then covered with fiberglass and epoxy for stiffness.'],
    ['V3', 'One piece per hull, sealed with epoxy. No fiberglass on the first boat.'],
  ],
};
const DECK = {
  facts: [['Length', '963 mm'], ['Width', '233 mm'], ['Thickness', '12 mm'], ['Overlap', '23 mm longer']],
  why: [
    'Closes the top of the hull and screws down around its edge, so it can come off whenever we need to reach the batteries and electronics.',
    'It’s slightly bigger than the hull, 963 × 233 mm over a 940 × 221 mm hull, so it covers the hull’s top edge all the way round.',
    'The bridge stands on the two deck plates.',
  ],
  history: [['V3', 'New: each hull gets its own removable plate.']],
};
const PARTS = {
  'hull-port': { group: 'Hull', side: 'Port', title: 'Port hull', kind: 'hull',
    facts: [['Length', '940 mm'], ['Width', '220 mm'], ['Depth', '253 mm'], ['Walls', '6 mm']], why: HULL.why, history: HULL.history },
  'hull-stbd': { group: 'Hull', side: 'Starboard', title: 'Starboard hull', kind: 'hull',
    facts: [['Length', '940 mm'], ['Width', '222 mm'], ['Depth', '255 mm'], ['Walls', '6 mm']],
    why: [...HULL.why, 'A row of bosses inside takes the screws that hold the deck plate down.', 'It carries the boat’s name near the stern.'],
    history: HULL.history },
  'deck-port': { group: 'Deck plate', side: 'Port', title: 'Port deck plate', kind: 'deck', ...DECK },
  'deck-stbd': { group: 'Deck plate', side: 'Starboard', title: 'Starboard deck plate', kind: 'deck', ...DECK },
  'bridge': { group: 'Bridge', side: 'Across the hulls', title: 'Bridge', kind: 'bridge',
    facts: [['Span', '602 mm'], ['Length', '335 mm'], ['Height', '119 mm above deck'], ['Walls', '10 mm']],
    why: [
      'The bridge arches from hull to hull instead of lying flat, so it stays high above the water and leaves the space between the hulls open.',
      'The look comes from commercial survey catamarans such as the EvoLogics Sonobot.',
      'A hollow shell with 10 mm walls. Each end stands on a hull’s deck plate.',
      'It sits toward the stern, from 25 mm ahead of the middle of the hulls to 310 mm behind it.',
    ],
    history: [['V1', 'A clear acrylic deck tied the hulls together and carried the winch.'], ['V3', 'A raised arch.']] },
  'name': { group: 'Name', side: 'Starboard', title: 'Dr. Eams', kind: 'name',
    facts: [['Letters', '7'], ['Height', '30 mm'], ['Raised', '5 mm'], ['Length', '190 mm']],
    why: ['The boat’s name, a play on D.R.E.A.M.S.', 'Raised letters near the stern on the starboard hull.'], history: [] },
};
const OVERVIEW = [['Length', '963 mm'], ['Beam', '733 mm'], ['Height', '368 mm'], ['Hulls', '940 mm long'], ['Hull spacing', '500 mm'], ['Clear between', '279 mm']];

/* geometry, in metres: +x starboard, +y up, -z toward the bow */
const EXPLODE = { 'hull-port': [-0.17, 0, 0], 'hull-stbd': [0.17, 0, 0], 'deck-port': [-0.17, 0.17, 0], 'deck-stbd': [0.17, 0.17, 0], 'bridge': [0, 0.4, 0], 'name': [0.23, 0, 0] };
const VIEWS = { iso: [1, 0.62, -0.62], side: [1, 0.04, 0], bow: [0.3, 0.2, -1], top: [0, 1, 0.012], below: [0.25, -1, 0.05], cutz: [0.45, 0.42, -1], cutx: [-1, 0.36, 0.3] };
/* layer views: the cut keeps what lies aft of it (z) or to starboard of it (x) */
const CUTS = { z: { normal: [0, 0, 1], start: 0.143, view: 'cutz' }, x: { normal: [1, 0, 0], start: -0.25, view: 'cutx' } };

/* ---------- page ---------- */
const $ = id => document.getElementById(id);
const stage = $('bx-stage');
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const EYE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/><path class="slash" d="M4 4l16 16"/></svg>';
const parts = {};   // part id -> three.js object, once the model has loaded
let selected = null, scene3d = null;

function buildList() {
  $('bx-parts').innerHTML = GROUPS.map(g => `<div class="bx-group"><p class="label"><span>${esc(g.name)}</span><span>×${g.ids.length}</span></p>` +
    g.ids.map(id => { const p = PARTS[id];
      return `<div class="bx-row" data-id="${id}"><button type="button" class="bx-pick" data-id="${id}"><span class="bx-sw" style="--c:${SWATCH[p.kind]}"></span>` +
        `<span class="bx-nm">${esc(p.title)}</span><span class="bx-dm" data-dims="${id}"></span></button>` +
        `<button type="button" class="bx-eye" data-id="${id}" aria-pressed="true" aria-label="Hide ${esc(p.title)}">${EYE}</button></div>`; }).join('') + '</div>').join('');
}

function renderCard(id) {
  const card = $('bx-card'), p = id && PARTS[id];
  if (!p) {
    card.innerHTML = '<div class="bx-top"><p class="label">The whole boat</p><div class="bx-title"><h3>D.R.E.A.M.S V3</h3><span class="chip incad">In CAD</span></div></div>' +
      `<dl class="bx-facts">${OVERVIEW.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>` +
      '<p class="bx-hint">Pick a part on the boat or in the list to see what it is and why it’s built that way. Pull the boat apart, or turn on a layer view and slide the cut to look inside the hulls and the bridge.</p>';
    return;
  }
  const hist = p.history.length ? `<h4>How it changed</h4><ol class="bx-history">${p.history.map(([v, t]) => `<li${v === 'V3' ? ' class="now"' : ''}><span class="v">${v}</span><span>${esc(t)}</span></li>`).join('')}</ol>` : '';
  const hidden = parts[id] && !parts[id].visible;
  card.innerHTML = `<div class="bx-top"><p class="label">${esc(p.group)}&nbsp;· ${esc(p.side)}</p><div class="bx-title"><h3>${esc(p.title)}</h3></div></div>` +
    `<dl class="bx-facts">${p.facts.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>` +
    `<h4>Why it’s built this way</h4><ul class="bx-why">${p.why.map(t => `<li>${esc(t)}</li>`).join('')}</ul>${hist}` +
    '<div class="bx-acts"><button type="button" class="bx-tool" data-act="only">Show only this part</button>' +
    `<button type="button" class="bx-tool" data-act="all">Back to the whole boat</button>${hidden ? '<span class="label">Hidden in the model</span>' : ''}</div>`;
}

function select(id) {
  selected = id && PARTS[id] ? id : null;
  document.querySelectorAll('.bx-row').forEach(r => r.setAttribute('aria-current', String(r.dataset.id === selected)));
  renderCard(selected);
  if (scene3d) scene3d.highlight(selected);
}

function setVisible(id, on) {
  if (!parts[id]) return;
  parts[id].visible = on;
  const row = document.querySelector(`.bx-row[data-id="${id}"]`), eye = row && row.querySelector('.bx-eye');
  if (row) { row.classList.toggle('off', !on); eye.setAttribute('aria-pressed', String(on)); eye.setAttribute('aria-label', `${on ? 'Hide' : 'Show'} ${PARTS[id].title}`); }
  if (id === selected) renderCard(id);
  if (scene3d) scene3d.redraw();
}

function fail(msg) {
  const s = $('bx-status');
  s.textContent = msg; s.classList.add('error'); s.hidden = false;
}

if (stage) {
  buildList();
  renderCard(null);
  $('bx-parts').addEventListener('click', e => {
    const eye = e.target.closest('.bx-eye'), pick = e.target.closest('.bx-pick');
    if (eye) setVisible(eye.dataset.id, !(parts[eye.dataset.id] && parts[eye.dataset.id].visible));
    else if (pick) select(selected === pick.dataset.id ? null : pick.dataset.id);
  });
  $('bx-show-all').addEventListener('click', () => Object.keys(parts).forEach(id => setVisible(id, true)));
  $('bx-card').addEventListener('click', e => {
    const b = e.target.closest('[data-act]'); if (!b || !selected) return;
    if (b.dataset.act === 'only') Object.keys(parts).forEach(id => setVisible(id, id === selected));
    else { Object.keys(parts).forEach(id => setVisible(id, true)); select(null); }
  });
  addEventListener('keydown', e => { if (e.key === 'Escape' && selected) select(null); });

  const go = () => start().catch(() => fail('This browser can’t show the 3D model. The picture shows the boat as it stands in CAD.'));
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver(entries => { if (entries.some(en => en.isIntersecting)) { io.disconnect(); go(); } }, { rootMargin: '600px 0px' });
    io.observe(stage);
  } else go();
}

/* ---------- 3D ---------- */
async function start() {
  const [THREE, { OrbitControls }, { GLTFLoader }, { RoomEnvironment }] = await Promise.all([
    import('three'), import('three/addons/controls/OrbitControls.js'),
    import('three/addons/loaders/GLTFLoader.js'), import('three/addons/environments/RoomEnvironment.js')]);
  const canvas = $('bx-view'), tip = $('bx-tip');
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.VSMShadowMap;
  renderer.localClippingEnabled = true;

  const scene = new THREE.Scene();
  scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.95;
  const camera = new THREE.PerspectiveCamera(28, 1, 0.01, 60);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = !reduceMotion;
  controls.autoRotateSpeed = 0.7;
  const sun = new THREE.DirectionalLight(0xffffff, 1.6);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.radius = 14;
  sun.shadow.blurSamples = 20;
  scene.add(sun, sun.target);

  const cutPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
  const MATS = {
    hull: new THREE.MeshPhysicalMaterial({ color: SWATCH.hull, roughness: 0.42, clearcoat: 0.8, clearcoatRoughness: 0.1 }),   // epoxy gloss
    deck: new THREE.MeshStandardMaterial({ color: SWATCH.deck, roughness: 0.5 }),
    bridge: new THREE.MeshStandardMaterial({ color: SWATCH.bridge, roughness: 0.46 }),
    name: new THREE.MeshStandardMaterial({ color: SWATCH.name, roughness: 0.32, metalness: 0.15 }),
  };
  for (const m of Object.values(MATS)) Object.assign(m, { polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1, clipShadows: true });
  const edgeMat = new THREE.LineBasicMaterial({ color: '#1C6E9E', transparent: true, opacity: 0.95 });
  /* where a layer view cuts a wall, the wall's inside shows, drawn flat in ink so the section reads like a drawing */
  const capMat = new THREE.MeshBasicMaterial({ color: '#0D2E44', side: THREE.BackSide, clippingPlanes: [cutPlane] });

  const meshes = [], caps = [], edgeCache = {};
  const box = new THREE.Box3();
  let ptsAll = [], needs = true, explodeTarget = 0, explode = 0, tween = null, cutAxis = null, sweeping = false, edgesShown = null;

  function size() {
    const w = stage.clientWidth, h = stage.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(1, h);
    camera.updateProjectionMatrix();
    needs = true;
  }
  new ResizeObserver(size).observe(stage);
  size();

  /* a camera placement that frames these points, centred, to margin m of the view */
  function frameFor(dirArr, m, pts) {
    const dir = new THREE.Vector3(...dirArr).normalize(), q = new THREE.Vector3();
    const cam = new THREE.PerspectiveCamera(camera.fov, camera.aspect, 0.01, 200);
    const target = new THREE.Box3().setFromPoints(pts).getCenter(new THREE.Vector3());
    const place = d => { cam.position.copy(target).addScaledVector(dir, d); cam.lookAt(target); cam.updateMatrixWorld(); };
    const extent = () => { let x0 = 9, x1 = -9, y0 = 9, y1 = -9; for (const p of pts) { q.copy(p).project(cam); x0 = Math.min(x0, q.x); x1 = Math.max(x1, q.x); y0 = Math.min(y0, q.y); y1 = Math.max(y1, q.y); } return [x0, x1, y0, y1]; };
    let dist = 5;
    for (let pass = 0; pass < 3; pass++) {
      let lo = 0.05, hi = 60;
      for (let k = 0; k < 32; k++) { const d = (lo + hi) / 2; place(d); const [x0, x1, y0, y1] = extent(); if (Math.max(-x0, x1, -y0, y1) <= m) hi = d; else lo = d; }
      dist = hi; place(dist);
      const [x0, x1, y0, y1] = extent(), halfH = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) * dist;
      const right = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 0), up = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 1);
      target.addScaledVector(right, (x0 + x1) / 2 * halfH * cam.aspect).addScaledVector(up, (y0 + y1) / 2 * halfH);
    }
    place(dist);
    return { pos: cam.position.clone(), target };
  }

  function goTo(name, instant) {
    const f = frameFor(VIEWS[name], 0.84, ptsAll);
    document.querySelectorAll('.bx-views button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.view === name)));
    tween = { from: camera.position.clone(), to: f.pos, fromT: controls.target.clone(), toT: f.target, t0: performance.now(), dur: instant || reduceMotion ? 0 : 750 };
  }
  function stepTween(now) {
    if (!tween) return false;
    const k = tween.dur ? Math.min(1, (now - tween.t0) / tween.dur) : 1;
    const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
    const a = tween.from.clone().sub(tween.fromT), b = tween.to.clone().sub(tween.toT), la = a.length(), lb = b.length();
    const d = a.normalize().lerp(b.normalize(), e);
    if (d.lengthSq() < 1e-6) d.copy(b);
    const t = tween.fromT.clone().lerp(tween.toT, e);
    camera.position.copy(t).addScaledVector(d.normalize(), la + (lb - la) * e);
    controls.target.copy(t);
    if (k >= 1) tween = null;
    return true;
  }

  function applyExplode() {
    const s = explode * explode * (3 - 2 * explode);
    for (const [id, o] of Object.entries(parts)) {
      const off = EXPLODE[id] || [0, 0, 0], b = o.userData.base;
      o.position.set(b.x + off[0] * s, b.y + off[1] * s, b.z + off[2] * s);
    }
    needs = true;
  }
  function setExplode(v) {
    explodeTarget = v;
    const txt = v < 0.02 ? 'Assembled' : v > 0.98 ? 'Fully apart' : 'Apart';
    $('bx-explode').value = String(Math.round(v * 100)); $('bx-explode').setAttribute('aria-valuetext', txt); $('bx-explode-out').textContent = txt;
  }

  /* layer views */
  const cutRange = axis => axis === 'z' ? [box.min.z + 0.002, box.max.z - 0.002] : [box.min.x + 0.002, box.max.x - 0.002];
  function cutLabel(axis, at) {
    if (axis === 'z') return `${Math.round((at - box.min.z) * 1000)} mm aft of the bow`;
    const mm = Math.round(Math.abs(at) * 1000);
    return mm < 2 ? 'On the centreline' : `${mm} mm to ${at < 0 ? 'port' : 'starboard'} of the centreline`;
  }
  function setCutAt(at) {
    const [lo, hi] = cutRange(cutAxis);
    at = Math.min(hi, Math.max(lo, at));
    cutPlane.constant = -at;   // keeps points where normal · p >= at
    const txt = cutLabel(cutAxis, at);
    $('bx-cut').value = String(Math.round((at - lo) / (hi - lo) * 1000)); $('bx-cut').setAttribute('aria-valuetext', txt); $('bx-cut-out').textContent = txt;
    needs = true;
  }
  function setCut(axis, moveCamera) {
    cutAxis = axis === 'off' ? null : axis;
    const on = !!cutAxis;
    for (const m of [...Object.values(MATS), edgeMat]) { m.clippingPlanes = on ? [cutPlane] : []; m.needsUpdate = true; }
    caps.forEach(c => { c.visible = on; });
    document.querySelectorAll('.bx-seg button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.cut === (cutAxis || 'off'))));
    $('bx-cut-row').hidden = !on;
    needs = true;
    if (!on) { sweep(false); return; }
    cutPlane.normal.set(...CUTS[cutAxis].normal);
    setCutAt(CUTS[cutAxis].start);
    if (moveCamera) goTo(CUTS[cutAxis].view);
  }
  function sweep(on) {
    sweeping = on && !!cutAxis;
    $('bx-sweep').setAttribute('aria-pressed', String(sweeping));
    $('bx-sweep').textContent = sweeping ? 'Stop' : 'Sweep';
  }

  function edgesFor(id) {
    if (edgeCache[id]) return edgeCache[id];
    const ms = [];
    parts[id].traverse(o => { if (o.isMesh && !o.userData.cap) ms.push(o); });
    return (edgeCache[id] = ms.map(m => { const e = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, 24), edgeMat); e.raycast = () => {}; m.add(e); return e; }));
  }
  const partOf = obj => { while (obj) { if (obj.userData && PARTS[obj.userData.id]) return obj.userData.id; obj = obj.parent; } return null; };
  const shown = obj => { while (obj) { if (!obj.visible) return false; obj = obj.parent; } return true; };
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  function pickAt(x, y) {
    const r = canvas.getBoundingClientRect();
    ndc.set(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    for (const h of ray.intersectObjects(meshes, false)) {
      if (!shown(h.object) || (cutAxis && cutPlane.distanceToPoint(h.point) < 0)) continue;   // hidden, or cut away
      return partOf(h.object);
    }
    return null;
  }
  const stopSpin = () => { controls.autoRotate = false; $('bx-spin').setAttribute('aria-pressed', 'false'); };

  /* load the model */
  const gltf = await new GLTFLoader().loadAsync('media/boat-v3.glb').catch(() => null);
  if (!gltf) { fail('The 3D model didn’t load. Reload the page to try again.'); return; }
  const root = gltf.scene;
  root.traverse(o => {
    if (o.userData && PARTS[o.userData.id]) parts[o.userData.id] = o;
    if (o.isMesh) { o.castShadow = true; meshes.push(o); }
  });
  for (const [id, o] of Object.entries(parts)) {
    o.traverse(m => { if (m.isMesh) m.material = MATS[PARTS[id].kind]; });
    o.userData.base = o.position.clone();
    const s = o.userData.size_mm, cell = document.querySelector(`[data-dims="${id}"]`);
    if (s && cell) cell.textContent = `${Math.round(s.length)} × ${Math.round(s.beam)} × ${Math.round(s.height)}`;
  }
  for (const m of meshes) { const cap = new THREE.Mesh(m.geometry, capMat); cap.userData.cap = true; cap.visible = false; cap.raycast = () => {}; m.add(cap); caps.push(cap); }
  scene.add(root);
  box.setFromObject(root);
  const center = box.getCenter(new THREE.Vector3()), radius = box.getSize(new THREE.Vector3()).length() / 2;
  root.updateMatrixWorld(true);
  for (const m of meshes) {
    const p = m.geometry.attributes.position, step = Math.max(1, Math.floor(p.count / 600));
    for (let i = 0; i < p.count; i += step) ptsAll.push(new THREE.Vector3().fromBufferAttribute(p, i).applyMatrix4(m.matrixWorld));
  }

  const ground = new THREE.Mesh(new THREE.PlaneGeometry(radius * 3, radius * 3), new THREE.ShadowMaterial({ opacity: 0.16 }));
  ground.rotation.x = -Math.PI / 2; ground.position.y = box.min.y - 0.002; ground.receiveShadow = true;
  scene.add(ground);
  sun.position.copy(center).add(new THREE.Vector3(0.9, 2.6, -0.7).multiplyScalar(radius));
  sun.target.position.copy(center);
  const sc = sun.shadow.camera; sc.left = sc.bottom = -radius * 1.6; sc.right = sc.top = radius * 1.6; sc.near = 0.1; sc.far = radius * 8; sc.updateProjectionMatrix();
  controls.minDistance = radius * 0.6; controls.maxDistance = radius * 7;

  scene3d = {
    redraw: () => { needs = true; },
    highlight: id => {
      if (edgesShown && edgeCache[edgesShown]) edgeCache[edgesShown].forEach(e => { e.visible = false; });
      edgesShown = id;
      if (id) edgesFor(id).forEach(e => { e.visible = true; });
      needs = true;
    },
  };

  /* controls */
  controls.addEventListener('start', () => { stopSpin(); tween = null; });
  let down = null, hoverQueued = false;
  canvas.addEventListener('pointerdown', e => { down = { x: e.clientX, y: e.clientY, t: performance.now() }; });
  canvas.addEventListener('pointerup', e => {
    if (!down) return;
    const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y), quick = performance.now() - down.t < 600;
    down = null;
    if (moved < 6 && quick) select(pickAt(e.clientX, e.clientY));
  });
  canvas.addEventListener('pointermove', e => {
    if (e.pointerType !== 'mouse' || hoverQueued) return;
    hoverQueued = true;
    requestAnimationFrame(() => {
      hoverQueued = false;
      const id = e.buttons ? null : pickAt(e.clientX, e.clientY), r = stage.getBoundingClientRect();
      tip.hidden = !id;
      if (id) { tip.textContent = PARTS[id].title; tip.style.left = `${e.clientX - r.left}px`; tip.style.top = `${e.clientY - r.top}px`; }
      canvas.style.cursor = id ? 'pointer' : '';
    });
  });
  canvas.addEventListener('pointerleave', () => { tip.hidden = true; });
  document.querySelector('.bx-views').addEventListener('click', e => { const b = e.target.closest('button[data-view]'); if (b) { stopSpin(); goTo(b.dataset.view); } });
  $('bx-explode').addEventListener('input', e => { stopSpin(); setExplode(Number(e.target.value) / 100); });
  $('bx-spin').addEventListener('click', () => { controls.autoRotate = !controls.autoRotate; $('bx-spin').setAttribute('aria-pressed', String(controls.autoRotate)); needs = true; });
  $('bx-reset').addEventListener('click', () => { setExplode(0); setCut('off'); Object.keys(parts).forEach(id => setVisible(id, true)); select(null); goTo('iso'); });
  document.querySelector('.bx-seg').addEventListener('click', e => { const b = e.target.closest('button[data-cut]'); if (b) { stopSpin(); setCut(b.dataset.cut, true); } });
  $('bx-cut').addEventListener('input', e => { if (!cutAxis) return; sweep(false); const [lo, hi] = cutRange(cutAxis); setCutAt(lo + (hi - lo) * Number(e.target.value) / 1000); });
  $('bx-sweep').addEventListener('click', () => { stopSpin(); sweep(!sweeping); });

  /* loop: draw only when something changed */
  let last = performance.now();
  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    let moving = false;
    if (Math.abs(explodeTarget - explode) > 1e-4) { explode += (explodeTarget - explode) * (1 - Math.exp(-dt * 9)); applyExplode(); moving = true; }
    else if (explode !== explodeTarget) { explode = explodeTarget; applyExplode(); }
    if (sweeping && cutAxis) { const [lo, hi] = cutRange(cutAxis); let at = -cutPlane.constant + dt * 0.12; if (at > hi) at = lo; setCutAt(at); moving = true; }
    moving = stepTween(now) || moving;
    if (controls.update()) moving = true;
    if (needs || moving) { renderer.render(scene, camera); needs = false; }
    requestAnimationFrame(frame);
  }
  goTo('iso', true);
  if (selected) scene3d.highlight(selected);
  requestAnimationFrame(frame);
  $('bx-status').hidden = true;
  stage.classList.add('ready');
  const hashId = location.hash.slice(1);
  if (PARTS[hashId]) select(hashId);
}
