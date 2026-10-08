/* D.R.E.A.M.S V2 command center — backend-less demo shim.
 *
 * The dashboard (index.html) is the V2 command_center.html served by FastAPI on
 * the boat's Pi 5, nearly unmodified. This file stands in for that backend:
 *   - window.fetch is answered locally for every /api, /vision, /stepper, /pico
 *     route the page uses, with response shapes taken from pi5/server/app.py +
 *     models.py (tag v2-final);
 *   - window.WebSocket is replaced for /ws/telemetry, /ws/health and /ws/pico by
 *     an in-page socket fed from a small simulator;
 *   - the camera <img> (/video?cam=...) and recording <video> sources are drawn
 *     on a canvas instead of streamed.
 * The simulator runs a survey loop on Jamaica Pond, Boston, in "sim" mode, the
 * same way the real stack's simulator reported itself.
 * Anything the page asks for that isn't handled here is logged with
 * console.warn("[demo] unhandled", path).
 */
(function () {
  'use strict';

  // ------------------------------------------------------------------ helpers
  const D2R = Math.PI / 180, R2D = 180 / Math.PI;
  const now = () => Date.now() / 1000;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const wrap180 = (d) => { d = ((d + 180) % 360 + 360) % 360 - 180; return d; };
  const wrap360 = (d) => ((d % 360) + 360) % 360;
  const rnd = (a, b) => a + Math.random() * (b - a);
  const r1 = (v) => Math.round(v * 10) / 10;
  const r2 = (v) => Math.round(v * 100) / 100;
  const r3 = (v) => Math.round(v * 1000) / 1000;
  const M_LAT = 111320;
  const mLon = (lat) => 111320 * Math.cos(lat * D2R);

  function offset(lat, lon, northM, eastM) {
    return [lat + northM / M_LAT, lon + eastM / mLon(lat)];
  }
  function distBrg(lat1, lon1, lat2, lon2) {
    const n = (lat2 - lat1) * M_LAT, e = (lon2 - lon1) * mLon((lat1 + lat2) / 2);
    return [Math.hypot(n, e), wrap360(Math.atan2(e, n) * R2D)];
  }

  // ------------------------------------------------------------ the pond + plan
  // Jamaica Pond, Jamaica Plain, Boston. Waypoints sit well inside the shoreline.
  const POND = { lat: 42.3165, lon: -71.1205 };
  const HOME = (() => { const [la, lo] = offset(POND.lat, POND.lon, 150, 290); return { lat: +la.toFixed(6), lon: +lo.toFixed(6) }; })();  // off the east shore

  function wp(n, e, type, label) {
    const [lat, lon] = offset(POND.lat, POND.lon, n, e);
    return { lat: +lat.toFixed(6), lon: +lon.toFixed(6), type, max_time: 300, label };
  }
  const SURVEY = [
    wp(230, 70, 'path', ''),
    wp(250, 0, 'data', 'N1'),
    wp(170, -110, 'path', ''),
    wp(20, -170, 'data', 'W1'),
    wp(-120, -150, 'path', ''),
    wp(-200, -20, 'data', 'S1'),
    wp(-160, 140, 'path', ''),
    wp(0, 210, 'data', 'E1'),
    wp(160, 200, 'path', ''),
    wp(70, 40, 'data', 'C1'),
  ];
  const T0 = now();
  const savedPaths = {
    'Jamaica Pond — survey loop': { name: 'Jamaica Pond — survey loop', waypoints: SURVEY, updated: T0 - 3600 * 26 },
    'Jamaica Pond — east transect': {
      name: 'Jamaica Pond — east transect', updated: T0 - 3600 * 74,
      waypoints: [wp(200, 180, 'path', ''), wp(110, 220, 'data', 'T1'), wp(10, 200, 'data', 'T2'),
                  wp(-90, 170, 'data', 'T3'), wp(-170, 110, 'path', '')],
    },
    'Boathouse shakedown': {
      name: 'Boathouse shakedown', updated: T0 - 3600 * 120,
      waypoints: [wp(150, 240, 'path', ''), wp(200, 150, 'path', ''), wp(120, 160, 'data', 'TEST')],
    },
  };

  // Bathymetry: Jamaica Pond is a kettle pond, ~15 m at its deepest.
  function depthAt(lat, lon) {
    const n = (lat - POND.lat) * M_LAT - 50, e = (lon - POND.lon) * mLon(lat) - 35;
    const r = Math.hypot(n / 310, e / 290);
    return clamp(15 * (1 - r * r) + Math.sin(n / 37) * 0.8, 1.5, 15.5);
  }

  // ------------------------------------------------------------------- state
  const S = {
    lat: 0, lon: 0, heading: 0, speed: 0, yawRate: 0,
    thrL: 0, thrR: 0, battPct: 81.4, winchPct: 88, elecPct: 76,
    mtL: 27, mtR: 27, curL: 0, curR: 0,
    estopped: false,
    maxSpeed: 2.5, cruise: 40, trimL: 1.0, trimR: 1.0,
    winchDown: 50, winchUp: -50,
    curE: -0.035, curN: -0.025,          // sim water current (m/s)
    manual: { enabled: false, speed: 40, surge: 0, yaw: 0, last: 0 },
    mode: 'mission',                     // mission | goto | heading | idle
    gotoT: null, holdHdg: null, holding: false,
    avoiding: false, xte: 0,
    obstacles: [], nextObsId: 1,
    objects: [], nextObjId: 1,
    pod: [],
  };
  const mission = {
    name: 'Jamaica Pond — survey loop', wps: SURVEY.map((w) => ({ ...w })),
    running: true, paused: false, current_wp: 3, phase: 'TRANSIT', phaseT: 0,
    depth: 0, bottom: 0, sample_count: 2, elapsed_s: 612, autoLoop: true, restartAt: 0,
  };
  // Start mid-survey: on the leg into WP4 (W1) with two sites already sampled.
  (function () {
    const a = SURVEY[2], b = SURVEY[3];
    S.lat = a.lat + (b.lat - a.lat) * 0.1; S.lon = a.lon + (b.lon - a.lon) * 0.1;
    S.heading = distBrg(S.lat, S.lon, b.lat, b.lon)[1]; S.speed = 2.3;
  })();
  // Charted marks the vision memory "already knows" (permanent = cyan).
  function addObject(cls, lat, lon, category, sightings, conf) {
    S.objects.push({ id: S.nextObjId++, class_name: cls, category, lat, lon,
      confidence: conf, sightings, confirmed: true, first: now() - rnd(300, 2400), last: now() - rnd(20, 600), dist: null });
  }
  (function () {
    let p = offset(POND.lat, POND.lon, 120, -150); addObject('buoy', p[0], p[1], 'permanent', 14, 0.86);
    p = offset(POND.lat, POND.lon, -150, -95); addObject('buoy', p[0], p[1], 'permanent', 9, 0.81);
    p = offset(POND.lat, POND.lon, 150, 330); addObject('dock', p[0], p[1], 'permanent', 22, 0.9);
    // Some pod history so POD STATUS has something to say.
    for (let i = 0; i < 2; i++) {
      S.pod.push({ timestamp: now() - 420 + i * 200, water_temp: 15.8 - i * 0.4, salinity_ec: 402 + i * 7,
        light_pct: 18 - i * 4, bottom_contact: true, leak_detected: false, pressure_depth_m: 9.6 + i * 2.1 });
    }
  })();

  // ------------------------------------------------------- vision / stepper
  const V = { yolo: true, seg: true, avoid: true, survey: 7, primary: null, prevDist: {},
    dets: [], anomaly: 0.04, water: 'clear', buoyOn: true };
  const CAM = { jpeg_quality: 60, stream_fps: 15, detect_max_fps: 8, conf: 0.4, imgsz: 320,
    track_class: '', track_conf: 0, left: 0, right: 2 };
  const STEP = { mode: 'SCAN', angle: 0, target: null, autoRescan: true, sweepDir: 1,
    gotoA: null, locked: false, limits: [-170, 170], sweep: [-90, 90] };

  function computeDetections() {
    const dets = [];
    const seen = S.objects.concat(S.obstacles.map((o) => ({ class_name: o.label === 'obstacle' ? 'debris' : o.label,
      lat: o.lat, lon: o.lon, obstacle: o })));
    seen.forEach((o) => {
      const [d, b] = distBrg(S.lat, S.lon, o.lat, o.lon);
      const rb = wrap180(b - S.heading);
      if (d < 55 && Math.abs(rb) < 40) {
        dets.push({ label: o.class_name, confidence: r3(clamp(0.92 - d / 120 + rnd(-0.04, 0.04), 0.35, 0.97)),
          distance_m: r1(d), rb, obj: o });
      }
    });
    dets.sort((a, b) => a.distance_m - b.distance_m);
    V.dets = V.yolo ? dets : [];
    // primary threat (anything that isn't a fixed mark)
    const threat = V.dets.find((d) => !['buoy', 'dock'].includes(d.label) && d.distance_m < 30);
    if (threat) {
      const prev = V.prevDist[threat.label];
      const approach = prev == null ? 'APPROACHING' : (threat.distance_m < prev - 0.05 ? 'APPROACHING'
        : threat.distance_m > prev + 0.05 ? 'RECEDING' : 'STATIC');
      V.prevDist[threat.label] = threat.distance_m;
      const crit = (threat.label === 'person' && threat.distance_m < 20) || threat.distance_m < 9;
      V.primary = { class_name: threat.label, threat_level: crit ? 'CRITICAL' : 'WARNING',
        distance_m: threat.distance_m, approach_vector: approach, confidence: threat.confidence,
        bearing_deg: r1(threat.rb) };
    } else { V.primary = null; V.prevDist = {}; }
    V.water = V.primary ? 'obstacle' : (V.dets.some((d) => d.label === 'debris') ? 'debris' : 'clear');
    V.anomaly = clamp((V.dets.length ? 0.12 + 0.05 * V.dets.length : 0.03) + rnd(-0.015, 0.015), 0, 1);
    for (const d of V.dets) {
      if (d.obj && d.obj.id && S.objects.includes(d.obj)) {
        d.obj.last = now(); d.obj.dist = d.distance_m;
        if (Math.random() < 0.3) d.obj.sightings++;
      }
    }
  }

  function stepStepper(dt) {
    const tgt = V.dets.find((d) => !CAM.track_class || d.label === CAM.track_class);
    const confOk = tgt && tgt.confidence >= (CAM.track_conf || 0);
    if (STEP.mode === 'SLEEP') { STEP.locked = false; return; }
    if ((STEP.mode === 'SCAN' || STEP.mode === 'TRACK') && tgt && confOk) {
      STEP.locked = true; STEP.target = { label: tgt.label, conf: tgt.confidence };
      const want = clamp(tgt.rb, STEP.limits[0], STEP.limits[1]);
      const prev = STEP.angle;
      STEP.angle += clamp(want - STEP.angle, -60 * dt, 60 * dt);
      STEP.offset = r1(want - STEP.angle);
      STEP.rate = (STEP.angle - prev) / dt;
      if (STEP.mode === 'SCAN') STEP.mode = 'TRACK';
      return;
    }
    STEP.locked = false; STEP.target = null; STEP.offset = null; STEP.rate = 0;
    if (STEP.mode === 'TRACK' && STEP.autoRescan) STEP.mode = 'SCAN';
    if (STEP.mode === 'SCAN') {
      STEP.angle += STEP.sweepDir * 22 * dt;
      if (STEP.angle > STEP.sweep[1]) { STEP.angle = STEP.sweep[1]; STEP.sweepDir = -1; }
      if (STEP.angle < STEP.sweep[0]) { STEP.angle = STEP.sweep[0]; STEP.sweepDir = 1; }
    } else if (STEP.gotoA != null) {
      STEP.angle += clamp(STEP.gotoA - STEP.angle, -45 * dt, 45 * dt);
      if (Math.abs(STEP.gotoA - STEP.angle) < 0.05) STEP.gotoA = null;
    }
  }

  // ------------------------------------------------------------- simulator
  function navTarget() {
    if (S.mode === 'mission' && mission.running) {
      const w = mission.wps[mission.current_wp];
      return w ? { lat: w.lat, lon: w.lon } : null;
    }
    if (S.mode === 'goto' && S.gotoT) return S.gotoT;
    return null;
  }
  function prevPoint() {
    if (S.mode === 'mission' && mission.current_wp > 0) return mission.wps[mission.current_wp - 1];
    return S.legStart || null;
  }

  function steerTo(desired, base) {
    let off = 0;
    S.avoiding = false;
    if (V.avoid) {
      for (const o of S.obstacles) {
        const [d, b] = distBrg(S.lat, S.lon, o.lat, o.lon);
        const rb = wrap180(b - S.heading);
        const clear = d - o.radius_m;
        if (clear < 14 && Math.abs(rb) < 75) {
          S.avoiding = true;
          const mag = 55 * clamp(1 - clear / 14, 0.25, 1);
          const o2 = (rb >= 0 ? -1 : 1) * mag;
          if (Math.abs(o2) > Math.abs(off)) off = o2;
        }
      }
    }
    const err = wrap180(desired + off - S.heading);
    const b2 = base * clamp(1 - Math.abs(err) / 140, 0.3, 1);
    const turn = clamp(err * 0.7, -45, 45);
    return [clamp(b2 + turn, -100, 100), clamp(b2 - turn, -100, 100), err];
  }

  function setMissionPhase(p) { mission.phase = p; mission.phaseT = 0; }

  function advanceWp() {
    mission.current_wp++;
    setMissionPhase('TRANSIT');
    if (mission.current_wp >= mission.wps.length) {
      mission.current_wp = mission.wps.length - 1;
      setMissionPhase('COMPLETE');
      mission.running = false;
      if (mission.autoLoop) mission.restartAt = now() + 12;
    }
  }
  function startMission() {
    mission.running = true; mission.paused = false; mission.current_wp = 0;
    mission.sample_count = 0; mission.elapsed_s = 0; mission.depth = 0;
    setMissionPhase('TRANSIT'); S.mode = 'mission'; S.holding = false;
    S.manual.enabled = false;
  }
  function abortMission(autoLoopOff) {
    if (mission.running) { mission.running = false; mission.paused = false; }
    if (autoLoopOff) mission.autoLoop = false;
    mission.restartAt = 0;
  }

  let nav = { distance_m: 0, bearing_deg: 0, heading_error: 0, target: null };
  function tick(dt) {
    let L = 0, R = 0, err = 0;
    S.holding = false; S.avoiding = false;
    const t = navTarget();
    nav.target = t;
    if (t) {
      const [d, b] = distBrg(S.lat, S.lon, t.lat, t.lon);
      nav.distance_m = d; nav.bearing_deg = b;
      const p = prevPoint();
      if (p) {   // cross-track error off the leg (+ = starboard of the line)
        const [dp, bp] = distBrg(p.lat, p.lon, S.lat, S.lon);
        const [, bl] = distBrg(p.lat, p.lon, t.lat, t.lon);
        S.xte = dp * Math.sin((bp - bl) * D2R);
      } else S.xte = 0;
    }

    if (S.estopped) {
      L = R = 0;
    } else if (S.manual.enabled) {
      if (now() - S.manual.last > 0.75) { S.manual.stale = true; L = R = 0; }
      else { S.manual.stale = false; [L, R] = manualMix(); }
    } else if (S.mode === 'mission' && mission.running && !mission.paused) {
      if (mission.phase === 'TRANSIT') {
        const base = S.cruise * clamp(nav.distance_m / 10, 0.35, 1);
        [L, R, err] = steerTo(nav.bearing_deg, base);
        if (nav.distance_m < 4) {
          const w = mission.wps[mission.current_wp];
          if (w.type === 'data') { mission.bottom = depthAt(S.lat, S.lon); setMissionPhase('WINCH_DOWN'); }
          else advanceWp();
        }
      } else if (mission.phase === 'WINCH_DOWN' || mission.phase === 'SAMPLING' || mission.phase === 'WINCH_UP') {
        S.holding = true;                       // station-keep over the site
        const [h1, h2, e2] = steerTo(wrap360(Math.atan2(-S.curE, -S.curN) * R2D), 6);
        [L, R, err] = S.speed > 0.15 ? [-8, -8, e2] : [h1 * 0.5, h2 * 0.5, e2];
        mission.phaseT += dt;
        const down = 0.012 * S.winchDown, up = 0.012 * Math.abs(S.winchUp);
        if (mission.phase === 'WINCH_DOWN') {
          mission.depth = Math.min(mission.bottom, mission.depth + down * dt);
          if (mission.depth >= mission.bottom) setMissionPhase('SAMPLING');
        } else if (mission.phase === 'SAMPLING') {
          if (mission.phaseT > 7) {
            mission.sample_count++;
            V.survey += Math.random() < 0.5 ? 1 : 0;
            S.pod.push({ timestamp: now(), water_temp: r2(waterTemp() - mission.depth * 0.38),
              salinity_ec: r1(ec() + rnd(-6, 6)), light_pct: Math.round(clamp(60 - mission.depth * 4.5, 2, 60)),
              bottom_contact: true, leak_detected: false, pressure_depth_m: r2(mission.depth) });
            if (S.pod.length > 200) S.pod.shift();
            setMissionPhase('WINCH_UP');
          }
        } else {
          mission.depth = Math.max(0, mission.depth - up * dt);
          if (mission.depth <= 0) advanceWp();
        }
      }
    } else if (S.mode === 'goto' && S.gotoT) {
      if (nav.distance_m < 4 || S.gotoArrived) {
        S.gotoArrived = true; S.holding = true;
        [L, R, err] = nav.distance_m > 6 ? steerTo(nav.bearing_deg, 15) : [0, 0, 0];
      } else {
        [L, R, err] = steerTo(nav.bearing_deg, S.cruise * clamp(nav.distance_m / 10, 0.35, 1));
      }
    } else if (S.mode === 'heading' && S.holdHdg != null) {
      [L, R, err] = steerTo(S.holdHdg, S.cruise);
    }
    if (!mission.running && mission.restartAt && now() > mission.restartAt && S.mode === 'mission'
        && !S.manual.enabled && !S.estopped) { mission.restartAt = 0; startMission(); }
    if (mission.running && !mission.paused) mission.elapsed_s += dt;

    nav.heading_error = err;
    L = Math.round(L * S.trimL); R = Math.round(R * S.trimR);
    S.thrL = L; S.thrR = R;

    // boat dynamics: differential thrust → yaw rate, mean thrust → surge
    const yawCmd = (L - R) * 0.42;
    S.yawRate += (yawCmd - S.yawRate) * clamp(dt * 2.2, 0, 1);
    S.heading = wrap360(S.heading + S.yawRate * dt);
    const vT = clamp(S.maxSpeed * ((L + R) / 2) / 40, -0.5 * S.maxSpeed, 2 * S.maxSpeed);
    S.speed += (vT - S.speed) * clamp(dt / 2.0, 0, 1);
    const n = S.speed * Math.cos(S.heading * D2R) + S.curN;
    const e = S.speed * Math.sin(S.heading * D2R) + S.curE;
    [S.lat, S.lon] = offset(S.lat, S.lon, n * dt, e * dt);
    S.sog = Math.hypot(n, e);

    // power + ESCs
    const load = (Math.abs(L) + Math.abs(R)) / 200;
    S.battPct = Math.max(5, S.battPct - (0.0004 + load * 0.006) * dt);
    S.winchPct = Math.max(5, S.winchPct - ((mission.phase === 'WINCH_DOWN' || mission.phase === 'WINCH_UP') ? 0.004 : 0) * dt);
    S.elecPct = Math.max(5, S.elecPct - 0.0009 * dt);
    S.mtL += ((26 + Math.abs(L) * 0.32) - S.mtL) * dt / 25;
    S.mtR += ((26 + Math.abs(R) * 0.32) - S.mtR) * dt / 25;
    S.curL = Math.abs(L) > 1 ? Math.pow(Math.abs(L), 1.45) * 0.026 : 0;
    S.curR = Math.abs(R) > 1 ? Math.pow(Math.abs(R), 1.45) * 0.026 : 0;
  }
  function manualMix() {
    const sc = S.manual.speed / 100;
    let l = (S.manual.surge + S.manual.yaw) * sc * 100, r = (S.manual.surge - S.manual.yaw) * sc * 100;
    const pk = Math.max(Math.abs(l), Math.abs(r));
    if (pk > 100) { l = l * 100 / pk; r = r * 100 / pk; }
    return [Math.round(l), Math.round(r)];
  }
  function waterTemp() { return 16.2 + Math.sin((S.lat - POND.lat) * 9000) * 0.35 + Math.sin(now() / 90) * 0.05; }
  function ec() { return 405 + Math.sin((S.lon - POND.lon) * 7000) * 14; }

  let lastTick = performance.now(), visT = 0;
  setInterval(() => {
    const t = performance.now();
    let dt = (t - lastTick) / 1000; lastTick = t;
    dt = Math.min(dt, 1);              // background tabs throttle timers; don't teleport
    const steps = Math.max(1, Math.ceil(dt / 0.1));
    for (let i = 0; i < steps; i++) tick(dt / steps);
    visT += dt;
    if (visT >= 0.25) { computeDetections(); stepStepper(visT); visT = 0; }
    sentryCheck();
  }, 100);

  // ----------------------------------------------------- response builders
  function telOut() {
    const pct = Math.round(S.battPct);
    return {
      lat: r6(S.lat), lon: r6(S.lon), heading: r1(S.heading),
      speed_knots: r2(Math.max(0, (S.sog || 0) * 1.94384 + rnd(-0.03, 0.03))),
      batt_v: r2(15.4 + 4.6 * S.battPct / 100), batt_pct: pct,
      hull: 'DRY', mt_left: r1(S.mtL), mt_right: r1(S.mtR), health: '111111',
      curr_left: r1(S.curL), curr_right: r1(S.curR),
      fix_quality: 1, sats: 11 + (Math.random() < 0.15 ? 1 : 0), hdop: r2(0.86 + rnd(-0.05, 0.05)),
      gps_source: 'sim', gps_sats_visible: 17, gps_sats_tracked: 13, gps_best_snr: 44,
    };
  }
  function r6(v) { return Math.round(v * 1e6) / 1e6; }
  function envOut() {
    return {
      air_temp: 19, air_humidity: 63, water_temp: r1(waterTemp()), water_ec: r1(ec()),
      water_light: Math.round(clamp(58 - mission.depth * 4.5 + rnd(-1, 1), 2, 70)),
      bottom_contact: mission.phase === 'SAMPLING' && mission.running,
    };
  }
  function navOut() {
    const t = nav.target;
    return {
      target_lat: t ? r6(t.lat) : null, target_lon: t ? r6(t.lon) : null,
      distance_m: t ? r1(nav.distance_m) : 0, bearing_deg: t ? r1(nav.bearing_deg) : 0,
      heading_error: r1(nav.heading_error), throttle_left: S.thrL, throttle_right: S.thrR,
      arrived: !!(t && nav.distance_m < 4), active: !!t && !S.manual.enabled,
      cross_track_m: r2(S.xte), course_deg: r1(S.heading), avoiding: S.avoiding,
      current_set_deg: r1(wrap360(Math.atan2(S.curE, S.curN) * R2D)),
      current_drift_ms: r2(Math.hypot(S.curE, S.curN)),
      station_keeping: S.holding,
      manual: S.manual.enabled, manual_speed: S.manual.speed, manual_stale: !!(S.manual.enabled && S.manual.stale),
      pico_estopped: S.estopped,
    };
  }
  function missionOut() {
    return { name: mission.name, running: mission.running, paused: mission.paused,
      current_wp: mission.current_wp, total_wps: mission.wps.length, phase: mission.phase,
      est_depth_m: r2(mission.depth), sample_count: mission.sample_count, elapsed_s: r1(mission.elapsed_s) };
  }
  function boatOut() {
    const t = telOut(), e = envOut();
    return {
      connected: true, lat: t.lat, lon: t.lon, heading: t.heading, speed_knots: t.speed_knots,
      batt_v: t.batt_v, batt_pct: t.batt_pct,
      elec_v: r2(15.6 + 4.4 * S.elecPct / 100), elec_pct: Math.round(S.elecPct),
      winch_v: r2(15.6 + 4.4 * S.winchPct / 100), winch_pct: Math.round(S.winchPct),
      hull: 'DRY', hull_left: false, hull_right: false,
      mt_left: t.mt_left, mt_right: t.mt_right, curr_left: t.curr_left, curr_right: t.curr_right,
      health: t.health, health_flags: { GPS: true, IMU: true, P_BAT: true, E_BAT: true, MOT: true, POD: true },
      air_temp: e.air_temp, air_humidity: e.air_humidity, enc_temp: r1(33.5 + Math.sin(now() / 200)), enc_humidity: 41.0,
      water_temp: e.water_temp, water_ec: e.water_ec, water_light: e.water_light, bottom_contact: e.bottom_contact,
      alert: null,
    };
  }
  function visionOut() {
    return {
      water_state: V.water, anomaly_score: r3(V.anomaly), tier1_fps: r1(14.6 + rnd(-0.6, 0.4)),
      tier2_active: V.yolo && V.dets.length > 0, tier3_active: !!V.primary,
      primary_threat: V.primary, tracking_engaged: !!V.primary && STEP.locked,
      tracked_object: V.primary ? V.primary.class_name : null,
      tracked_distance_m: V.primary ? V.primary.distance_m : null,
      detections_count: V.dets.length, yolo_enabled: V.yolo, segmentation_enabled: V.seg,
      avoidance_enabled: V.avoid, avoiding: S.avoiding,
      wave: { enabled: true, incoming: false, bearing_deg: r1(rnd(-8, 8)), severity: r3(rnd(0.02, 0.07)), ttc_s: null, horizon_y: 0.42 },
      survey_logged: V.survey, seg_backend: 'classical', confirm: null, mission_alert: null,
      object_memory: { confirmed: S.objects.length, candidates: 0 },
    };
  }
  function detsOut() { return V.dets.map((d) => ({ label: d.label, confidence: d.confidence, distance_m: d.distance_m })); }
  const BOOT = now() - 3600 * 5 - 1260;
  let net = { rx: 380, tx: 2400 };
  function healthOut() {
    net.rx += (rnd(250, 600) - net.rx) * 0.3; net.tx += (rnd(1900, 3100) - net.tx) * 0.3;
    const tr = V.dets[0];
    const temp = 57.5 + V.dets.length * 1.2 + rnd(-0.8, 0.8);
    const s = STEP;
    return {
      temp_c: r1(temp), throttled: 'OK', throttled_raw: '0x0',
      cpu_percent: [rnd(38, 62), rnd(30, 55), rnd(44, 71), rnd(22, 41)].map(r1),
      ram_used_gb: r1(3.1 + rnd(-0.05, 0.05)), ram_total_gb: 7.9,
      disk_used_gb: 21.4, disk_total_gb: 58.0, swap_used_gb: 0.1, swap_total_gb: 0.5,
      uptime_s: Math.round(now() - BOOT), proc_count: 214 + Math.round(rnd(-2, 2)),
      load_avg: [r2(2.1 + rnd(-0.3, 0.3)), 1.96, 1.83],
      net_rx_kbps: r1(net.rx), net_tx_kbps: r1(net.tx),
      clock_mhz: 2400.0, volts: { core: 0.87, sdram_c: 1.1, sdram_i: 1.1, sdram_p: 1.1 },
      camera_fps: r1(clamp(CAM.stream_fps, 1, 15) - rnd(0, 0.5)),
      detect_fps: V.yolo ? r1(clamp(CAM.detect_max_fps, 1, 8.4) - rnd(0, 0.4)) : null,
      detections: V.yolo ? detsOut() : [],
      pod_ok: true, pod_leak: false, pod_age_s: r1(rnd(0.2, 2)),
      stepper_angle: r1(s.angle), stepper_state: s.mode === 'SCAN' ? 'SCANNING' : s.mode,
      stepper_target_locked: s.locked, stepper_target: s.target,
      stepper_no_lock_reason: (!s.locked && (s.mode === 'SCAN' || s.mode === 'TRACK')) ? 'no detections in view' : '',
      stepper_auto_rescan: s.autoRescan, stepper_track_warning: '',
      stepper_centered: s.locked && Math.abs(s.offset || 0) < 2, stepper_offset_deg: s.locked ? s.offset : null,
      stepper_target_rate_dps: s.locked ? r1(s.rate || 0) : null, stepper_lead_deg: s.locked ? r1((s.rate || 0) * 0.15) : null,
      track: tr ? { label: tr.label, confidence: tr.confidence, distance_m: tr.distance_m,
        cx: Math.round(320 + tr.rb * 8), cy: 190, x1: Math.round(300 + tr.rb * 8), y1: 170,
        x2: Math.round(340 + tr.rb * 8), y2: 210 } : null,
      vision: visionOut(), boat: boatOut(), timestamp: now(),
    };
  }

  // ------------------------------------------------------------ ESC (AM32)
  const ESC_FIELDS = [
    ['name', [5, 17], 'text', 'ESC Name', 'info', { editable: false }],
    ['firmware', [3, 5], 'fw', 'Firmware', 'info', { editable: false }],
    ['boot', 0, 'boot', 'Config Status', 'info', { editable: false }],
    ['motor_kv', 26, 'num', 'Motor KV', 'info', { scale: 40, unit: 'KV', editable: false }],
    ['poles', 27, 'num', 'Motor Poles', 'info', { editable: false }],
    ['bidir', 18, 'bool', 'Bi-Directional', 'drive', { important: true, warn_when: false,
      help: 'ON = center-neutral instant reverse (1.5 ms neutral). REQUIRED: the navigator commands negative throttle to pivot and to bear away. OFF ⇒ reverse pulses just idle and the boat can\'t turn in place or back off.' }],
    ['rc_car_rev', 38, 'bool', 'RC Car Reversing', 'drive', { warn_when: true,
      help: 'Keep OFF for the boat. It adds brake-on-first-reverse + double-tap to change direction (for RC cars); the boat needs immediate proportional reverse, which plain Bi-Directional already gives.' }],
    ['dir_reversed', 17, 'bool', 'Direction Reversed', 'drive', {
      help: 'Flip if a forward command spins THIS hull backward, so forward command → forward thrust on both hulls.' }],
    ['telemetry', 31, 'bool', '30 ms Telemetry', 'drive', { important: true,
      help: 'ON streams KISS temp+current to the dashboard. Needs the ESC\'s TX pad wired to Pico GP16 (L) / GP11 (R). See docs/esc_telemetry.md.' }],
    ['lvc_enable', 36, 'bool', 'Low-Voltage Cutoff', 'protect', {
      help: 'Per-ESC pack cutoff backstop (the firmware also watches pack V on GP26).' }],
    ['lvc_cell_v', 37, 'num', 'LVC Threshold', 'protect', { base: 2.5, scale: 0.01, unit: 'V/cell', vmin: 2.5, vmax: 3.6, ui_step: 0.05,
      help: '~3.0 V/cell for the 5S (2× M18 parallel) drive rail. Match the pack cutoff.' }],
    ['stuck_prot', 22, 'bool', 'Stuck-Rotor Protect', 'protect', {
      help: 'Relax / OFF for a survey boat — a prop loading up in weeds shouldn\'t trip a restart mid-mission.' }],
    ['stall_prot', 29, 'bool', 'Stall Protection', 'protect', {}],
    ['brake_stop', 28, 'bool', 'Brake on Stop', 'protect', {
      help: 'OFF lets the prop freewheel at neutral (differential steering); braking wastes energy and fights the turn.' }],
    ['sinusoidal', 19, 'bool', 'Sinusoidal Startup', 'tune', { help: 'ON = smoother, quieter low-speed starts under a big boat prop.' }],
    ['timing', 23, 'num', 'Timing Advance', 'tune', { scale: 7.5, unit: '°', vmin: 0, vmax: 30, ui_step: 7.5,
      help: 'Raise if low-speed startup is rough (larger low-Kv props often want more).' }],
    ['startup_pow', 25, 'num', 'Startup Power', 'tune', { unit: '%', vmin: 50, vmax: 150, ui_step: 5 }],
    ['pwm_khz', 24, 'num', 'PWM Frequency', 'tune', { unit: 'kHz', vmin: 8, vmax: 48, ui_step: 1 }],
    ['comp_pwm', 20, 'bool', 'Complementary PWM', 'tune', {}],
    ['var_pwm', 21, 'bool', 'Variable PWM Freq', 'tune', {}],
    ['beep_vol', 30, 'num', 'Beacon Volume', 'tune', { vmin: 0, vmax: 11, ui_step: 1 }],
  ].map(([key, off, kind, label, group, o]) => ({ key, off, kind, label, group, base: o.base || 0,
    scale: o.scale || 1, unit: o.unit || '', vmin: o.vmin == null ? null : o.vmin, vmax: o.vmax == null ? null : o.vmax,
    ui_step: o.ui_step != null ? o.ui_step : (o.scale || 1), editable: o.editable !== false,
    important: !!o.important, warn_when: o.warn_when == null ? null : o.warn_when, help: o.help || '' }));
  const eeprom = new Array(176).fill(0);
  (function () {
    const e = eeprom; e[0] = 1; e[3] = 2; e[4] = 15;
    'NeutronRC G0'.split('').forEach((c, i) => { e[5 + i] = c.charCodeAt(0); });
    Object.assign(e, { 17: 0, 18: 1, 19: 1, 20: 1, 21: 0, 22: 1, 23: 2, 24: 24, 25: 100, 26: 55, 27: 14,
      28: 0, 29: 1, 30: 5, 31: 1, 36: 1, 37: 50, 38: 0 });
  })();
  function decimals(step) { return (step >= 1 && Number.isInteger(step)) ? 0 : (step >= 0.1 ? 1 : 2); }
  function decodeEeprom() {
    return ESC_FIELDS.map((f) => {
      const d = { key: f.key, label: f.label, group: f.group, kind: f.kind, editable: f.editable,
        important: f.important, help: f.help };
      if (f.kind === 'text') {
        const raw = eeprom.slice(f.off[0], f.off[1]); const z = raw.indexOf(0);
        const val = String.fromCharCode(...(z >= 0 ? raw.slice(0, z) : raw)).trim() || '(unnamed)';
        return Object.assign(d, { value: val, display: val, raw: raw.slice(0, z >= 0 ? z : raw.length) });
      }
      if (f.kind === 'fw') {
        const val = eeprom[f.off[0]] + '.' + eeprom[f.off[0] + 1];
        return Object.assign(d, { value: val, display: 'v' + val, raw: [eeprom[f.off[0]], eeprom[f.off[0] + 1]] });
      }
      if (f.kind === 'boot') {
        const ok = eeprom[f.off] === 1;
        return Object.assign(d, { value: ok, display: ok ? 'Configured' : 'UNCONFIGURED', raw: eeprom[f.off] });
      }
      if (f.kind === 'bool') {
        const val = !!eeprom[f.off];
        Object.assign(d, { value: val, display: val ? 'ON' : 'OFF', raw: eeprom[f.off] });
        if (f.warn_when != null) { d.warn_when = f.warn_when; if (val === f.warn_when) d.warn = true; }
        return d;
      }
      const raw = eeprom[f.off];
      const val = Math.round((f.base + raw * f.scale) * 1000) / 1000;
      return Object.assign(d, { value: val, raw, unit: f.unit, min: f.vmin, max: f.vmax, step: f.ui_step,
        display: val.toFixed(decimals(f.ui_step)) + (f.unit ? ' ' + f.unit : '') });
    });
  }
  function escMeta() {
    return {
      sim: true, port: '/dev/ttyAMA0',
      groups: [{ key: 'drive', label: 'Drive' }, { key: 'protect', label: 'Protection' },
               { key: 'tune', label: 'Tuning' }, { key: 'info', label: 'ESC Info' }],
      wiring: [
        { from: 'ESC signal', to: 'Pi pin 10  ·  GPIO15 / RXD0', note: 'direct' },
        { from: 'ESC signal', to: 'Pi pin 8   ·  GPIO14 / TXD0', note: 'via ~1 kΩ series resistor' },
        { from: 'ESC ground', to: 'Pi pin 6   ·  GND', note: 'common ground' },
      ],
      wiring_note: '3.3 V both sides — no level shifter. Use the ESC\'s SIGNAL pad (normally on Pico GP2 left / GP3 right). Move the ESC you want to configure onto these Pi pins, then back to the Pico afterward. Props OFF, boat out of the water.',
      setup_cmds: ['sudo dtoverlay uart0', 'sudo systemctl stop serial-getty@ttyAMA10.service',
        'sudo chown root:dialout /dev/ttyAMA0 && sudo chmod 660 /dev/ttyAMA0'],
    };
  }
  function escApply(changes) {
    const trial = eeprom.slice(); const changed = [];
    for (const [k, v] of Object.entries(changes)) {
      const f = ESC_FIELDS.find((x) => x.key === k);
      if (!f) throw new Error('unknown setting \'' + k + '\'');
      if (!f.editable) throw new Error(f.label + ' is read-only');
      let raw;
      if (f.kind === 'bool') raw = (v === true || ['1', 'on', 'true', 'yes', 'y'].includes(String(v).toLowerCase())) ? 1 : 0;
      else {
        const n = parseFloat(v);
        if (isNaN(n)) throw new Error(f.label + ' must be a number');
        if (f.vmin != null && n < f.vmin - 1e-9) throw new Error(f.label + ' must be ≥ ' + f.vmin + (f.unit ? ' ' + f.unit : ''));
        if (f.vmax != null && n > f.vmax + 1e-9) throw new Error(f.label + ' must be ≤ ' + f.vmax + (f.unit ? ' ' + f.unit : ''));
        raw = clamp(Math.round((n - f.base) / f.scale), 0, 255);
      }
      if (trial[f.off] !== raw) { trial[f.off] = raw; changed.push(k); }
    }
    for (let i = 0; i < trial.length; i++) eeprom[i] = trial[i];
    return changed;
  }

  // ------------------------------------------------------------ recordings
  const REC = { sentry: true, active: null, seq: 4, clips: [] };
  function clipName(t, seq, trig) {
    const d = new Date(t * 1000), p = (n) => String(n).padStart(2, '0');
    return 'clip-' + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + '-' + p(d.getHours()) + p(d.getMinutes())
      + p(d.getSeconds()) + '-' + String(seq).padStart(4, '0') + '-' + trig;
  }
  function makeClip(started, seq, reason, trigger, severity, dur) {
    const name = clipName(started, seq, trigger);
    return { name, file: name + '.webm', reason, trigger, severity, started, duration_s: dur,
      frames: Math.round(dur * 15), fps: 15, width: 640, height: 360, mime: 'video/webm', favorite: false,
      size_bytes: Math.round(dur * 15 * rnd(9000, 13000)) };
  }
  REC.clips.push(makeClip(T0 - 3600 * 2.4, 1, 'manual', 'manual', 'manual', 42.6));
  REC.clips.push(makeClip(T0 - 3600 * 1.1, 2, 'critical-threat:person', 'critical-threat', 'critical', 18.4));
  REC.clips.push(makeClip(T0 - 60 * 23, 3, 'estop', 'estop', 'warning', 12.0));
  REC.clips[1].favorite = true;
  function recStatus() {
    const c = REC.active;
    return { sentry_enabled: REC.sentry, recording: !!c, active_reason: c ? c.reason : null,
      active_trigger: c ? c.trigger : null, active_frames: c ? Math.round((now() - c.started) * 15) : 0,
      preroll_frames: 45, clip_count: REC.clips.length };
  }
  function recStart(reason, trigger) {
    if (REC.active) return REC.active;
    REC.active = { name: clipName(now(), REC.seq, trigger), reason, trigger, started: now() };
    REC.active.file = REC.active.name + '.webm';
    return REC.active;
  }
  function recStop() {
    const c = REC.active; if (!c) return null;
    REC.active = null;
    const sev = trigSeverity(c.reason);
    const m = makeClip(c.started, REC.seq++, c.reason, c.trigger, sev, r1(Math.max(1, now() - c.started + 3)));
    REC.clips.unshift(m);
    return m;
  }
  function trigSeverity(reason) {
    const base = reason.split(':')[0];
    return { manual: 'manual', 'critical-threat': 'critical', 'hull-leak': 'critical', 'pod-leak': 'critical' }[base] || 'warning';
  }
  let sentryUntil = 0;
  function sentryCheck() {
    const crit = V.primary && V.primary.threat_level === 'CRITICAL';
    if (REC.sentry && crit && !REC.active) { recStart('critical-threat:' + V.primary.class_name, 'critical-threat'); sentryUntil = now() + 6; }
    if (REC.active && REC.active.trigger === 'critical-threat') {
      if (crit) sentryUntil = now() + 6;
      else if (now() > sentryUntil) recStop();
    }
  }

  // ------------------------------------------------------------ pico (files)
  const PICO_FILES = ['boot.py', 'main.py', 'protocol.py', 'motors.py', 'sensors.py', 'pod_link.py', 'config.json'];
  const PICO_MAIN = '# MicroPython — Boat Pico (main.py)\n'
    + '# DEMO COPY: the dashboard is running without a boat, so this is a short\n'
    + '# illustrative stand-in for the real firmware, not the file itself.\n'
    + 'import time\nfrom protocol import Link\nfrom motors import Drive\nfrom sensors import Sensors\n\n'
    + 'link = Link(uart_id=0, baud=115200)\ndrive = Drive(left_pin=2, right_pin=3)\nsensors = Sensors()\n\n'
    + 'WATCHDOG_MS = 1500   # no heartbeat from the Pi for this long => ESTOP\n\n'
    + 'while True:\n    for msg in link.poll():\n        if msg.kind == "SET_THR":\n            drive.set(msg.left, msg.right)\n'
    + '        elif msg.kind == "ESTOP":\n            drive.estop()\n        elif msg.kind == "RESUME":\n            drive.resume()\n'
    + '    if link.ms_since_heartbeat() > WATCHDOG_MS:\n        drive.estop()\n'
    + '    link.send_tel(sensors.read_tel(), drive.status())\n    time.sleep_ms(100)\n';

  // ------------------------------------------------------------- the router
  function json(status, body) { return { status, body }; }
  const ok = (b) => json(200, b);
  const err = (status, detail) => json(status, { detail });

  function route(method, path, q, body) {
    const p = path.replace(/\/+$/, '');
    const seg = p.split('/');
    switch (method + ' ' + p) {
      case 'GET /api/status':
        return ok({ telemetry: telOut(), environment: envOut(), navigation: navOut(), mission: missionOut(), connected: true });
      case 'GET /api/telemetry': return ok(telOut());
      case 'GET /api/environment': return ok(envOut());
      case 'GET /api/network': return ok({ mode: 'auto', active_kind: 'wifi', active_interface: 'wlan0', online: true });
      case 'GET /api/pod/history': {
        const n = clamp(parseInt(q.get('limit') || '100', 10) || 100, 1, 5000);
        return ok(S.pod.slice(-n).reverse());
      }
      case 'GET /api/mission': return ok(missionOut());
      case 'POST /api/mission': {
        if (!body || !body.name || !Array.isArray(body.waypoints) || !body.waypoints.length) return err(400, 'Invalid mission data');
        mission.name = body.name;
        mission.wps = body.waypoints.map((w) => ({ lat: +w.lat, lon: +w.lon, type: w.type || 'data', max_time: w.max_time || 300, label: w.label || '' }));
        abortMission(false); mission.current_wp = 0; setMissionPhase('TRANSIT'); mission.depth = 0;
        mission.sample_count = 0; mission.elapsed_s = 0; mission.autoLoop = true;
        if (q.get('start') === 'true') { S.estopped = false; startMission(); }
        return ok(missionOut());
      }
      case 'POST /api/mission/start':
        if (!mission.wps.length) return err(400, 'No mission loaded');
        mission.autoLoop = true; startMission(); return ok({ status: 'started' });
      case 'POST /api/mission/pause': if (mission.running) mission.paused = true; return ok({ status: 'paused' });
      case 'POST /api/mission/resume': if (mission.running) mission.paused = false; S.mode = 'mission'; return ok({ status: 'resumed' });
      case 'POST /api/mission/abort': abortMission(true); return ok({ status: 'aborted' });
      case 'POST /api/mission/skip':
        if (mission.running) {
          if (mission.phase === 'TRANSIT') advanceWp();
          else if (mission.phase !== 'WINCH_UP') setMissionPhase('WINCH_UP');
        }
        return ok({ status: 'skipping' });
      case 'POST /api/goto': {
        const lat = +body.lat, lon = +body.lon;
        if (!(lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180)) return err(422, 'invalid coordinates');
        if (mission.running) abortMission(true);
        S.mode = 'goto'; S.gotoT = { lat, lon }; S.gotoArrived = false; S.legStart = { lat: S.lat, lon: S.lon };
        return ok({ status: 'navigating', lat, lon });
      }
      case 'POST /api/estop':
        if (mission.running) abortMission(true);
        S.manual.enabled = false; S.mode = 'idle'; S.gotoT = null; S.estopped = true;
        return ok({ status: 'emergency_stop' });
      case 'POST /api/resume': S.estopped = false; return ok({ status: 'resumed' });
      case 'GET /api/mission/waypoints':
        return ok(mission.wps.map((w) => ({ lat: w.lat, lon: w.lon, type: w.type, label: w.label })));
      case 'GET /api/paths':
        return ok(Object.values(savedPaths).sort((a, b) => b.updated - a.updated));
      case 'POST /api/paths':
        if (!body || !body.name || !Array.isArray(body.waypoints)) return err(422, 'invalid path');
        savedPaths[body.name] = { name: body.name, waypoints: body.waypoints, updated: now() };
        return ok({ status: 'saved', name: body.name, count: body.waypoints.length });
      case 'POST /api/heading': {
        const h = parseFloat(body && body.heading);
        if (isNaN(h) || h < 0 || h > 360) return err(400, 'heading must be 0–360');
        if (mission.running) abortMission(true);
        S.mode = 'heading'; S.holdHdg = h % 360; S.gotoT = null;
        return ok({ status: 'heading_set', heading: h % 360 });
      }
      case 'GET /api/sim/speed': return ok({ max_speed_mps: S.maxSpeed });
      case 'POST /api/sim/speed': {
        const v = body && body.max_speed_mps;
        if (v == null || !(v >= 0.1 && v <= 50)) return err(400, 'max_speed_mps must be 0.1–50.0');
        S.maxSpeed = +v; return ok({ status: 'ok', max_speed_mps: S.maxSpeed });
      }
      case 'GET /api/sim/current': return ok({ east_mps: S.curE, north_mps: S.curN });
      case 'POST /api/sim/current':
        S.curE = clamp(+body.east_mps || 0, -3, 3); S.curN = clamp(+body.north_mps || 0, -3, 3);
        return ok({ status: 'ok', east_mps: S.curE, north_mps: S.curN });
      case 'GET /api/sim/obstacles':
        return ok({ available: true, obstacles: S.obstacles.map((o) => ({ id: o.id, lat: r6(o.lat), lon: r6(o.lon), radius_m: o.radius_m, label: o.label })) });
      case 'POST /api/sim/obstacles': {
        const radius = parseFloat(body.radius_m != null ? body.radius_m : 4) || 4;
        const label = String(body.label != null ? body.label : 'obstacle');
        let lat = body.lat, lon = body.lon;
        if (lat == null || lon == null) {
          const ahead = parseFloat(body.ahead_m != null ? body.ahead_m : 15);
          [lat, lon] = offset(S.lat, S.lon, ahead * Math.cos(S.heading * D2R), ahead * Math.sin(S.heading * D2R));
        }
        const o = { id: S.nextObsId++, lat: +lat, lon: +lon, radius_m: radius, label };
        S.obstacles.push(o);
        if (label !== 'obstacle') {     // the sim object mapper "confirms" it after a few sightings
          setTimeout(() => {
            if (!S.obstacles.includes(o)) return;
            addObject(label, o.lat, o.lon, label === 'buoy' ? 'permanent' : 'transient', 3, 0.78);
          }, 2500);
        }
        return ok({ status: 'added', obstacle: { id: o.id, lat: r6(o.lat), lon: r6(o.lon), radius_m: o.radius_m, label: o.label }, count: S.obstacles.length });
      }
      case 'DELETE /api/sim/obstacles': S.obstacles = []; return ok({ status: 'cleared' });
      case 'GET /api/map/objects': {
        const t = now();
        S.objects = S.objects.filter((o) => o.category === 'permanent' || t - o.last < 240);
        return ok({ available: true, objects: S.objects.map((o) => {
          const [d] = distBrg(S.lat, S.lon, o.lat, o.lon);
          return { id: o.id, class_name: o.class_name, category: o.category, lat: r6(o.lat), lon: r6(o.lon),
            confidence: o.confidence, distance_m: r1(d), sightings: o.sightings, confirmed: true,
            age_s: r1(t - o.first), last_seen_s: r1(Math.max(0, t - o.last)) };
        }) });
      }
      case 'POST /api/map/objects/clear': S.objects = []; return ok({ status: 'cleared' });
      case 'GET /api/nav/throttle': return ok({ cruise_throttle: S.cruise });
      case 'POST /api/nav/throttle': {
        const v = body && body.cruise_throttle;
        if (v == null || !(v >= 1 && v <= 100)) return err(400, 'cruise_throttle must be 1–100');
        S.cruise = Math.round(v); return ok({ status: 'ok', cruise_throttle: S.cruise });
      }
      case 'GET /api/nav/motor-trim': return ok({ left: S.trimL, right: S.trimR });
      case 'POST /api/nav/motor-trim':
        for (const side of ['left', 'right']) {
          if (body[side] == null) continue;
          const v = parseFloat(body[side]);
          if (isNaN(v)) return err(400, side + ' must be a number');
          if (!(v >= 0.5 && v <= 1.5)) return err(400, side + ' must be 0.5–1.5');
          if (side === 'left') S.trimL = v; else S.trimR = v;
        }
        return ok({ left: S.trimL, right: S.trimR });
      case 'GET /api/manual': return ok(manualState());
      case 'POST /api/manual': {
        const v = body && body.enabled;
        if (typeof v !== 'boolean') return err(400, 'enabled must be a boolean');
        if (v && mission.running && !mission.paused) return err(409, 'Pause or abort the mission before taking manual control');
        S.manual.enabled = v; S.manual.surge = S.manual.yaw = 0; S.manual.last = now();
        if (v) { S.mode = 'idle'; S.gotoT = null; } else if (mission.running) S.mode = 'mission';
        return ok(manualState());
      }
      case 'POST /api/manual/drive': {
        if (!S.manual.enabled) return err(409, 'Manual override is not armed');
        const su = parseFloat(body.surge || 0), ya = parseFloat(body.yaw || 0);
        if (!isFinite(su) || !isFinite(ya)) return err(400, 'surge/yaw must be finite');
        S.manual.surge = clamp(su, -1, 1); S.manual.yaw = clamp(ya, -1, 1); S.manual.last = now();
        const [l, r] = manualMix();
        return ok({ ok: true, throttle_left: l, throttle_right: r, pico_estopped: S.estopped });
      }
      case 'POST /api/manual/speed': {
        const v = parseInt(body && body.speed, 10);
        if (isNaN(v)) return err(400, 'speed must be an integer 0–100');
        if (v < 0 || v > 100) return err(400, 'speed must be 0–100');
        S.manual.speed = v; return ok({ speed: v });
      }
      case 'POST /api/esc/passthrough':
        return err(400, 'ESC passthrough is hardware-only (not available in the demo)');
      case 'GET /api/esc/meta': return ok(escMeta());
      case 'POST /api/esc/read':
        return ok(Object.assign(escMeta(), { connected: true, flash: 'SIM', boot_configured: eeprom[0] === 1, fields: decodeEeprom() }));
      case 'POST /api/esc/write': {
        const ch = body && body.changes;
        if (!ch || typeof ch !== 'object' || !Object.keys(ch).length) return err(400, 'no changes given');
        try { const changed = escApply(ch); return ok({ sim: true, flash: 'SIM', changed, fields: decodeEeprom() }); }
        catch (e) { return err(400, e.message); }
      }
      case 'GET /api/winch/speed': return ok({ down_speed: S.winchDown, up_speed: S.winchUp });
      case 'POST /api/winch/speed':
        if (body.down_speed != null) { if (!(body.down_speed >= 1 && body.down_speed <= 100)) return err(400, 'down_speed must be 1–100'); S.winchDown = Math.round(body.down_speed); }
        if (body.up_speed != null) { if (!(body.up_speed >= -100 && body.up_speed <= -1)) return err(400, 'up_speed must be -100 to -1'); S.winchUp = Math.round(body.up_speed); }
        return ok({ status: 'ok', down_speed: S.winchDown, up_speed: S.winchUp });
      case 'POST /api/rth':
        if (mission.running) abortMission(true);
        S.mode = 'goto'; S.gotoT = { lat: HOME.lat, lon: HOME.lon }; S.gotoArrived = false; S.legStart = { lat: S.lat, lon: S.lon };
        return ok({ status: 'returning_home', lat: HOME.lat, lon: HOME.lon });
      case 'GET /api/camera': return ok(cameraState());
      case 'POST /api/camera':
        if (body.jpeg_quality != null) CAM.jpeg_quality = clamp(parseInt(body.jpeg_quality, 10) || 60, 20, 95);
        if (body.stream_fps != null) CAM.stream_fps = clamp(parseFloat(body.stream_fps) || 15, 1, 60);
        if (body.detect_max_fps != null) CAM.detect_max_fps = clamp(parseFloat(body.detect_max_fps) || 8, 0.5, 30);
        if (body.conf != null) CAM.conf = clamp(parseFloat(body.conf) || 0.4, 0.05, 0.95);
        if (body.imgsz != null) CAM.imgsz = clamp(parseInt(body.imgsz, 10) || 320, 160, 640);
        if (body.track_class != null) CAM.track_class = String(body.track_class);
        if (body.track_conf != null) CAM.track_conf = clamp(parseFloat(body.track_conf) || 0, 0, 1);
        if (body.buoy_enabled != null) V.buoyOn = !!body.buoy_enabled;
        if (body.detection_enabled != null) V.yolo = !!body.detection_enabled;
        return ok(cameraState());
      case 'GET /api/camera/devices':
        return ok({ available: true, devices: [
          { index: 0, name: 'Arducam OV9782 USB Camera (usb-xhci-hcd.0-1)', in_use: CAM.left === 0 || CAM.right === 0 },
          { index: 2, name: 'Arducam OV9782 USB Camera (usb-xhci-hcd.1-1)', in_use: CAM.left === 2 || CAM.right === 2 },
        ], left: CAM.left, right: CAM.right, left_open: true, right_open: CAM.right != null });
      case 'POST /api/camera/devices': {
        const left = parseInt(body.left, 10);
        if (isNaN(left)) return err(400, '\'left\' (int device index) is required');
        const right = (body.right == null || body.right === '') ? null : parseInt(body.right, 10);
        if (right === left) return err(400, 'left and right must be different devices');
        CAM.left = left; CAM.right = right;
        return ok({ status: 'ok', left, right, left_open: true, right_open: right != null });
      }
      case 'GET /api/recordings':
        return ok(Object.assign({ available: true }, recStatus(), { clips: REC.clips }));
      case 'POST /api/recordings/start': return ok({ status: 'recording', clip: (recStart('manual', 'manual'), { name: REC.active.name, file: REC.active.file, reason: 'manual', trigger: 'manual', severity: 'manual' }) });
      case 'POST /api/recordings/stop': return ok({ status: 'stopped', clip: recStop() });
      case 'POST /api/recordings/sentry':
        if (body && 'enabled' in body) REC.sentry = !!body.enabled;
        return ok(recStatus());
      case 'GET /vision/status': return ok(Object.assign(visionOut(), { available: true }));
      case 'GET /vision/threats':
        return ok({ available: true, threats: V.primary ? [V.primary] : [] });
      case 'POST /vision/yolo/toggle': V.yolo = !V.yolo; return ok({ yolo_enabled: V.yolo, message: 'YOLO ' + (V.yolo ? 'enabled' : 'disabled') });
      case 'POST /vision/segmentation/toggle': V.seg = !V.seg; return ok({ segmentation_enabled: V.seg, message: 'Segmentation ' + (V.seg ? 'enabled' : 'disabled') });
      case 'POST /vision/avoidance/toggle': V.avoid = !V.avoid; return ok({ avoidance_enabled: V.avoid, message: 'Avoidance ' + (V.avoid ? 'enabled' : 'disabled') });
      case 'GET /stepper/status': return ok(stepperStatus());
      case 'POST /stepper/command': return stepperCommand(body || {});
      case 'GET /pico/files': return ok({ available: true, files: PICO_FILES });
      case 'GET /pico/file': {
        const name = q.get('name') || 'main.py';
        if (!PICO_FILES.includes(name)) return ok({ available: true, name, content: '', reason: 'demo: no such file on the Pico' });
        const content = name === 'main.py' ? PICO_MAIN
          : '# ' + name + ' — demo placeholder (the real file lives on the boat\'s Pico)\n';
        return ok({ available: true, name, content });
      }
      case 'POST /pico/push': {
        if (!body || body.content == null) return err(400, 'missing \'content\'');
        const fn = body.filename || 'main.py';
        if (/[\\/]|\.\./.test(fn)) return err(400, 'invalid filename');
        if (!PICO_FILES.includes(fn)) PICO_FILES.push(fn);
        return ok({ ok: true, message: 'pushed ' + fn + ' and reset Pico (demo — nothing was flashed)' });
      }
      case 'GET /health': return ok(healthOut());
    }
    // parameterised routes
    if (method === 'DELETE' && seg[1] === 'api' && seg[2] === 'paths' && seg.length === 4) {
      const name = decodeURIComponent(seg[3]);
      if (!savedPaths[name]) return err(404, 'No such path');
      delete savedPaths[name]; return ok({ status: 'deleted', name });
    }
    if (seg[1] === 'api' && seg[2] === 'recordings' && seg.length >= 4) {
      const file = decodeURIComponent(seg[3]);
      const c = REC.clips.find((x) => x.file === file);
      if (method === 'DELETE' && seg.length === 4) {
        if (!c) return json(404, 'clip not found');
        REC.clips.splice(REC.clips.indexOf(c), 1); return ok({ status: 'deleted', file });
      }
      if (method === 'POST' && seg[4] === 'favorite') {
        if (!c) return json(404, 'clip not found');
        c.favorite = body && 'favorite' in body ? !!body.favorite : true;
        return ok({ status: 'ok', file, favorite: c.favorite });
      }
      if (method === 'GET' && seg.length === 4) return json(404, 'clip playback is not available in the demo');
    }
    return null;
  }
  function manualState() {
    return { enabled: S.manual.enabled, speed: S.manual.speed, stale: !!(S.manual.enabled && S.manual.stale),
      throttle_left: S.thrL, throttle_right: S.thrR, timeout_s: 0.75, pico_estopped: S.estopped };
  }
  function cameraState() {
    const floors = { person: r2(clamp(CAM.conf - 0.12, 0.05, 0.95)), swimmer: r2(clamp(CAM.conf - 0.15, 0.05, 0.95)),
      boat: r2(CAM.conf), buoy: 0.3 };
    return {
      camera_present: true, right_present: CAM.right != null, left_device: CAM.left, right_device: CAM.right,
      jpeg_quality: CAM.jpeg_quality, stream_fps: CAM.stream_fps, stream_fps_actual: r1(Math.min(CAM.stream_fps, 15) - 0.3),
      detection_enabled: V.yolo, detect_max_fps: CAM.detect_max_fps, conf: r2(CAM.conf),
      conf_floors: floors, conf_absolute: ['buoy'], buoy_available: true, buoy_enabled: V.buoyOn,
      imgsz: CAM.imgsz, model: 'models/yolo11n_ncnn_model', backend: 'ncnn', model_loaded: true,
      detect_fps: V.yolo ? r1(Math.min(CAM.detect_max_fps, 8.4) - 0.3) : null, track_class: CAM.track_class,
      classes: ['person', 'swimmer', 'boat', 'kayak', 'buoy', 'dock', 'debris', 'bird'],
      detections: detsOut(), track_conf: r2(CAM.track_conf),
    };
  }
  function stepperStatus() {
    const s = STEP;
    return { available: true, mock: false, angle: r1(s.angle), state: s.mode === 'SCAN' ? 'SCANNING' : s.mode,
      mode: s.mode, target_locked: s.locked, target: s.target, track_class: CAM.track_class,
      track_conf: r2(CAM.track_conf), auto_rescan: s.autoRescan, no_lock_reason: '', track_warning: '',
      centered: s.locked && Math.abs(s.offset || 0) < 2, offset_deg: s.locked ? s.offset : null,
      target_rate_dps: null, lead_deg: null, priority_classes: ['boat', 'buoy', 'kayak', 'person', 'swimmer'],
      limits: s.limits, sweep: s.sweep, has_slip_ring: false, bow_deg: 0 };
  }
  const STEP_CMDS = ['SCAN', 'STOP', 'GOTO', 'JOG', 'CENTER', 'SLEEP', 'WAKE', 'TRACK', 'HOLD', 'TRACK_ONLY'];
  function stepperCommand(b) {
    const cmd = String(b.command || '').toUpperCase();
    if (!STEP_CMDS.includes(cmd)) return err(400, 'command must be one of ' + STEP_CMDS.join(', '));
    const v = b.value;
    if (STEP.mode === 'SLEEP' && cmd !== 'WAKE' && cmd !== 'SLEEP') STEP.mode = 'HOLD';
    switch (cmd) {
      case 'SCAN': STEP.mode = 'SCAN'; STEP.autoRescan = true; STEP.gotoA = null; break;
      case 'TRACK': STEP.mode = 'TRACK'; break;
      case 'STOP': case 'HOLD': STEP.mode = 'HOLD'; STEP.gotoA = null; break;
      case 'CENTER': STEP.mode = 'HOLD'; STEP.gotoA = 0; break;
      case 'SLEEP': STEP.mode = 'SLEEP'; break;
      case 'WAKE': STEP.mode = 'HOLD'; break;
      case 'GOTO': {
        const a = parseFloat(v); if (isNaN(a)) return ok({ ok: false, error: 'GOTO needs an angle' });
        STEP.mode = 'HOLD'; STEP.gotoA = clamp(a, STEP.limits[0], STEP.limits[1]); break;
      }
      case 'JOG': {
        const a = parseFloat(v); if (isNaN(a)) return ok({ ok: false, error: 'JOG needs a step' });
        STEP.mode = 'HOLD'; STEP.gotoA = clamp((STEP.gotoA != null ? STEP.gotoA : STEP.angle) + a, STEP.limits[0], STEP.limits[1]); break;
      }
      case 'TRACK_ONLY': STEP.autoRescan = !(v === true || v === 'true' || v === 1); if (!STEP.autoRescan) STEP.mode = 'TRACK'; break;
    }
    return ok({ ok: true, command: cmd, status: stepperStatus() });
  }

  // ----------------------------------------------------------- fetch shim
  const realFetch = window.fetch ? window.fetch.bind(window) : null;
  const BACKEND = /\/(api|vision|stepper|pico)\/.*$|\/health$/;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  window.fetch = async function (input, init) {
    const rawUrl = (typeof input === 'string' || input instanceof URL) ? String(input) : input.url;
    const url = new URL(rawUrl, location.href);
    if (url.origin !== location.origin) return realFetch(input, init);
    const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    const m = url.pathname.match(BACKEND);
    if (!m) {
      console.warn('[demo] unhandled', method + ' ' + url.pathname);
      return realFetch(input, init);
    }
    let body = null;
    if (init && typeof init.body === 'string' && init.body) { try { body = JSON.parse(init.body); } catch (e) { body = null; } }
    await sleep(25 + Math.random() * 60);
    let res;
    try { res = route(method, m[0], url.searchParams, body || {}); }
    catch (e) { console.error('[demo] handler failed', m[0], e); res = err(500, 'demo handler error'); }
    if (!res) {
      console.warn('[demo] unhandled', method + ' ' + m[0]);
      res = err(404, 'not available in demo');
    }
    const text = typeof res.body === 'string' ? res.body : JSON.stringify(res.body);
    return new Response(text, { status: res.status,
      headers: { 'Content-Type': typeof res.body === 'string' ? 'text/plain' : 'application/json' } });
  };

  // ------------------------------------------------------- WebSocket shim
  const RealWS = window.WebSocket;
  class DemoSocket extends EventTarget {
    constructor(url, path) {
      super();
      this.url = url; this.protocol = ''; this.extensions = ''; this.bufferedAmount = 0; this.binaryType = 'blob';
      this.readyState = 0; this.onopen = null; this.onmessage = null; this.onclose = null; this.onerror = null;
      this._path = path; this._timers = []; this._state = {};
      setTimeout(() => {
        if (this.readyState !== 0) return;
        this.readyState = 1; this._fire('open');
        this._start();
      }, 40 + Math.random() * 80);
    }
    _fire(type, data, extra) {
      let ev;
      if (type === 'message') ev = new MessageEvent('message', { data, origin: location.origin });
      else if (type === 'close') ev = new CloseEvent('close', Object.assign({ code: 1000, reason: '', wasClean: true }, extra || {}));
      else ev = new Event(type);
      const h = this['on' + type];
      if (typeof h === 'function') { try { h.call(this, ev); } catch (e) { setTimeout(() => { throw e; }); } }
      this.dispatchEvent(ev);
    }
    _send(obj) { if (this.readyState === 1) this._fire('message', JSON.stringify(obj)); }
    _every(ms, fn, first) {
      if (first) fn();
      this._timers.push(setInterval(() => { if (this.readyState === 1) fn(); }, ms));
    }
    _start() {
      const p = this._path;
      if (p === '/ws/telemetry') {
        this._every(1000, () => this._send({ telemetry: telOut(), environment: envOut(), navigation: navOut(),
          mission: missionOut(), timestamp: now() }), true);
      } else if (p === '/ws/health') {
        this._every(1000, () => this._send(healthOut()), true);
      } else if (p === '/ws/pico') {
        this._every(400, () => this._picoLines(), true);
      } else if (p === '/ws/camera') {
        /* not used by this page; stays open and quiet */
      } else {
        console.warn('[demo] unhandled', 'WS ' + p);
        this._fire('error'); this.close(1011, 'not available in demo');
      }
    }
    _picoLines() {
      const st = this._state, t = performance.now() / 1000;
      if (!st.up) { st.up = true; this._send({ line: 'PICO: link UP', ts: now() }); }
      if (t - (st.tel || 0) >= 1) {
        st.tel = t; const x = telOut();
        this._send({ line: `PICO:TEL lat=${x.lat.toFixed(6)} lon=${x.lon.toFixed(6)} hdg=${x.heading.toFixed(1)} spd=${x.speed_knots.toFixed(1)}kn batt=${x.batt_v.toFixed(1)}V(${x.batt_pct}%) hull=${x.hull} L=${x.mt_left.toFixed(0)} R=${x.mt_right.toFixed(0)} health=${x.health}`, ts: now() });
      }
      if (t - (st.env || 0) >= 5) {
        st.env = t; const e = envOut();
        this._send({ line: `PICO:ENV air=${e.air_temp}°C/${e.air_humidity}% water=${e.water_temp.toFixed(1)}°C ec=${e.water_ec.toFixed(0)} light=${e.water_light} bottom=${e.bottom_contact ? 'YES' : 'no'}`, ts: now() });
      }
      if (S.estopped !== st.est) {
        if (st.est !== undefined || S.estopped)
          this._send({ line: S.estopped ? 'ERROR: [CRIT] ESTOP latched — motors disabled' : 'PICO:ALERT [INFO] RESUME — motors re-armed', ts: now() });
        st.est = S.estopped;
      }
    }
    send(data) {
      if (this.readyState === 0) throw new DOMException('Still in CONNECTING state.', 'InvalidStateError');
      if (this.readyState !== 1) return;
      if (this._path !== '/ws/pico') return;
      const text = String(data);
      setTimeout(() => {
        this._send({ line: '> ' + text, ts: now(), echo: true });
        setTimeout(() => this._send({ line: picoCommand(text), ts: now() }), 120);
      }, 30);
    }
    close(code, reason) {
      if (this.readyState >= 2) return;
      this.readyState = 2;
      this._timers.forEach(clearInterval); this._timers = [];
      setTimeout(() => { this.readyState = 3; this._fire('close', null, { code: code || 1000, reason: reason || '' }); }, 10);
    }
  }
  ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'].forEach((k, i) => {
    Object.defineProperty(DemoSocket, k, { value: i }); Object.defineProperty(DemoSocket.prototype, k, { value: i });
  });
  function picoCommand(text) {
    const parts = text.trim().split(/\s+/); const cmd = (parts[0] || '').toUpperCase();
    const known = ['ESTOP', 'GET_STATUS', 'HB', 'POLL_POD', 'REQ_TEL', 'RESUME', 'SET_HDG', 'SET_THR', 'SET_WINCH'];
    if (!cmd) return 'ERROR: empty command';
    if (!known.includes(cmd)) return `ERROR: unknown command '${cmd}' (try: ${known.join(', ')})`;
    const a = parts.slice(1);
    if (cmd === 'SET_THR' && (a.length < 2 || a.some((x) => isNaN(parseInt(x, 10))))) return 'ERROR: bad arguments for SET_THR';
    if ((cmd === 'SET_HDG' || cmd === 'SET_WINCH') && (!a.length || isNaN(parseFloat(a[0])))) return 'ERROR: bad arguments for ' + cmd;
    if (cmd === 'ESTOP') { if (mission.running) abortMission(true); S.manual.enabled = false; S.mode = 'idle'; S.gotoT = null; S.estopped = true; }
    if (cmd === 'RESUME') S.estopped = false;
    if (cmd === 'SET_HDG') { if (mission.running) abortMission(true); S.mode = 'heading'; S.holdHdg = wrap360(parseFloat(a[0])); }
    const reply = { GET_STATUS: 'STATUS', REQ_TEL: 'TEL', POLL_POD: 'POD' }[cmd] || 'ACK';
    if (cmd === 'SET_THR' && S.estopped) return 'PICO: SET_THR → NAK';
    return 'PICO: ' + cmd + ' → ' + reply;
  }
  function DemoWebSocket(url, protocols) {
    let u;
    try { u = new URL(url, location.href); } catch (e) { return new RealWS(url, protocols); }
    const m = u.pathname.match(/\/ws\/[^/]+$/);
    if (u.host === location.host && m) return new DemoSocket(String(url), m[0]);
    return protocols === undefined ? new RealWS(url) : new RealWS(url, protocols);
  }
  ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'].forEach((k, i) => Object.defineProperty(DemoWebSocket, k, { value: i }));
  DemoWebSocket.prototype = RealWS.prototype;
  window.WebSocket = DemoWebSocket;

  // -------------------------------------------------- camera (canvas frames)
  const cv = document.createElement('canvas'); cv.width = 640; cv.height = 360;
  const g = cv.getContext('2d');
  const camEls = new Set();
  const imgDesc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
  Object.defineProperty(HTMLImageElement.prototype, 'src', {
    configurable: true, enumerable: true,
    get() { return imgDesc.get.call(this); },
    set(v) {
      const s = String(v); const m = s.match(/\/video\?(?:.*&)?cam=([a-z]+)/) || (/\/video(\?|$)/.test(s) ? [0, 'left'] : null);
      if (m) {
        this.__demoView = m[1]; camEls.add(this);
        imgDesc.set.call(this, renderFrame(m[1]));
        return;
      }
      // CARTO tiles requested before the basemap swap below: don't fetch dead placeholders.
      if (/basemaps\.cartocdn\.com\//.test(s)) {
        imgDesc.set.call(this, 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7');
        return;
      }
      imgDesc.set.call(this, v);
    },
  });
  function treeLine(worldDeg) {   // height of the far shoreline at a compass bearing
    const a = worldDeg * D2R;
    return 26 + 9 * Math.sin(a * 3 + 1) + 6 * Math.sin(a * 7 + 2) + 4 * Math.sin(a * 17) + 2.5 * Math.sin(a * 41 + 0.5);
  }
  let frameN = 0;
  function renderFrame(view) {
    const W = 640, H = 360, t = performance.now() / 1000; frameN++;
    const roll = Math.sin(t * 0.9) * 1.2 + clamp(S.yawRate, -15, 15) * 0.12;
    const hy = H * 0.42 + Math.sin(t * 1.3) * 3;
    const pxDeg = W / 78;                       // ~78° horizontal FOV
    const parallax = view === 'right' ? -1 : 0;
    g.save();
    g.fillStyle = '#000'; g.fillRect(0, 0, W, H);
    g.translate(W / 2, H / 2); g.rotate(roll * D2R); g.translate(-W / 2, -H / 2);
    if (view === 'disparity') {
      // stereo depth colormap: near water = warm, far = cool, sky = invalid (dark)
      g.fillStyle = '#0b0b2a'; g.fillRect(-40, -40, W + 80, hy + 40);
      const grd = g.createLinearGradient(0, hy, 0, H);
      grd.addColorStop(0, '#2c2ca8'); grd.addColorStop(0.25, '#1f8ee8'); grd.addColorStop(0.5, '#2fe0a0');
      grd.addColorStop(0.75, '#e5e83a'); grd.addColorStop(1, '#e8501f');
      g.fillStyle = grd; g.fillRect(-40, hy, W + 80, H - hy + 40);
      g.fillStyle = '#3a1f9a';
      g.beginPath(); g.moveTo(-40, hy);
      for (let x = -40; x <= W + 40; x += 8) g.lineTo(x, hy - treeLine(S.heading + (x - W / 2) / pxDeg));
      g.lineTo(W + 40, hy); g.fill();
      for (let i = 0; i < 900; i++) {           // speckle, like block-matching noise
        const x = Math.random() * W, y = hy + Math.random() * (H - hy);
        g.fillStyle = Math.random() < 0.5 ? 'rgba(0,0,0,.25)' : 'rgba(255,255,255,.08)'; g.fillRect(x, y, 3, 2);
      }
      for (const d of V.dets) {
        const x = W / 2 + d.rb * pxDeg, y = hy + clamp(260 / d.distance_m, 4, 150), s = clamp(300 / d.distance_m, 6, 70);
        g.fillStyle = d.distance_m < 15 ? '#ff2d12' : '#ffb21a'; g.beginPath(); g.ellipse(x, y - s * 0.4, s * 0.55, s * 0.6, 0, 0, 7); g.fill();
      }
    } else {
      const sky = g.createLinearGradient(0, 0, 0, hy);
      sky.addColorStop(0, '#6f93b8'); sky.addColorStop(1, '#c9d7df');
      g.fillStyle = sky; g.fillRect(-40, -40, W + 80, hy + 40);
      // far shore: trees, then a sliver of path / wall
      g.fillStyle = '#2f4430';
      g.beginPath(); g.moveTo(-40, hy + 1);
      for (let x = -40; x <= W + 40; x += 6) g.lineTo(x, hy - treeLine(S.heading + (x + parallax * 6 - W / 2) / pxDeg));
      g.lineTo(W + 40, hy + 1); g.fill();
      g.fillStyle = '#4c5e45'; g.fillRect(-40, hy - 4, W + 80, 5);
      // water
      const wat = g.createLinearGradient(0, hy, 0, H);
      wat.addColorStop(0, '#5d7486'); wat.addColorStop(0.4, '#3d5464'); wat.addColorStop(1, '#22323e');
      g.fillStyle = wat; g.fillRect(-40, hy, W + 80, H - hy + 40);
      // reflection of the tree line
      g.fillStyle = 'rgba(40,58,44,.45)'; g.fillRect(-40, hy, W + 80, 14);
      // ripples, scrolling toward the camera with speed
      const flow = t * (0.6 + Math.abs(S.speed) * 0.9);
      g.strokeStyle = 'rgba(210,225,235,.18)'; g.lineWidth = 1;
      for (let i = 0; i < 70; i++) {
        const k = ((i * 0.6180339 + flow * 0.08) % 1);
        const y = hy + 6 + Math.pow(k, 2.2) * (H - hy);
        const x = ((i * 137.5 + S.heading * pxDeg * (0.3 + k)) % (W + 120)) - 60;
        const len = 8 + k * 60;
        g.beginPath(); g.moveTo(x, y); g.lineTo(x + len, y + Math.sin(i) * 0.6); g.stroke();
      }
      // objects in view
      for (const d of V.dets) {
        const x = W / 2 + d.rb * pxDeg + parallax * clamp(60 / d.distance_m, 0, 20);
        const y = hy + clamp(260 / d.distance_m, 4, 150), s = clamp(300 / d.distance_m, 5, 70);
        drawObject(d.label, x, y, s, t);
        d._box = [x - s * 0.7, y - s * 1.35, s * 1.4, s * 1.5];
      }
    }
    g.restore();
    if (view === 'left' && V.yolo) {                 // detection overlay, left view only
      g.font = '600 12px "IBM Plex Mono", monospace'; g.lineWidth = 2;
      V.dets.forEach((d, i) => {
        if (!d._box) return;
        const [x, y, w, h] = d._box, hi = i === 0;
        g.strokeStyle = hi ? '#7dff9a' : '#ffd23f'; g.strokeRect(x, y, w, h);
        const lab = d.label + ' ' + d.confidence.toFixed(2) + ' · ' + d.distance_m.toFixed(1) + 'm';
        g.fillStyle = 'rgba(0,0,0,.6)'; g.fillRect(x, y - 16, g.measureText(lab).width + 8, 15);
        g.fillStyle = hi ? '#7dff9a' : '#ffd23f'; g.fillText(lab, x + 4, y - 4);
        if (hi && STEP.locked) {
          const cx = x + w / 2, cy = y + h / 2, r = Math.max(w, h) * 0.75;
          g.strokeStyle = 'rgba(56,189,248,.9)'; g.beginPath(); g.arc(cx, cy, r, 0, 7); g.stroke();
        }
      });
    }
    if (view !== 'disparity') {                       // vision HUD (pipeline.annotate)
      g.font = '600 12px "IBM Plex Mono", monospace';
      const oy = H - 92;          // lower-left, clear of the page's CAM tag + TRACKING badge
      g.fillStyle = 'rgba(0,0,0,.45)'; g.fillRect(8, 8 + oy, 196, 38);
      g.fillStyle = V.water === 'clear' ? '#7dff9a' : '#ffb02e';
      g.fillText('WATER ' + V.water.toUpperCase(), 14, 23 + oy);
      g.fillStyle = '#9fb3c8'; g.fillText('ANOM', 14, 39 + oy);
      g.fillStyle = '#233'; g.fillRect(56, 31 + oy, 140, 8);
      g.fillStyle = V.anomaly >= 0.15 ? '#ffb02e' : '#38bdf8'; g.fillRect(56, 31 + oy, 140 * clamp(V.anomaly, 0, 1), 8);
    }
    const d = new Date();
    g.font = '500 11px "IBM Plex Mono", monospace'; g.fillStyle = 'rgba(230,240,250,.8)';
    g.fillText(d.toISOString().replace('T', ' ').slice(0, 19) + 'Z  SIM', 10, H - 10);
    // light vignette + grain
    const vg = g.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, W * 0.7);
    vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(0,0,0,.45)');
    g.fillStyle = vg; g.fillRect(0, 0, W, H);
    return cv.toDataURL('image/jpeg', clamp(CAM.jpeg_quality, 30, 95) / 100);
  }
  function drawObject(label, x, y, s, t) {
    const bob = Math.sin(t * 2 + x) * s * 0.04;
    y += bob;
    g.fillStyle = 'rgba(20,30,36,.35)'; g.beginPath(); g.ellipse(x, y + s * 0.08, s * 0.7, s * 0.12, 0, 0, 7); g.fill();
    if (label === 'buoy') {
      g.fillStyle = '#ff6a1a'; g.beginPath(); g.ellipse(x, y - s * 0.45, s * 0.42, s * 0.5, 0, 0, 7); g.fill();
      g.fillStyle = '#fff3e6'; g.fillRect(x - s * 0.42, y - s * 0.55, s * 0.84, s * 0.12);
      g.fillStyle = 'rgba(255,255,255,.35)'; g.beginPath(); g.ellipse(x - s * 0.15, y - s * 0.7, s * 0.1, s * 0.16, 0, 0, 7); g.fill();
    } else if (label === 'person' || label === 'swimmer') {
      g.fillStyle = '#e8b48a'; g.beginPath(); g.arc(x, y - s * 0.55, s * 0.22, 0, 7); g.fill();
      g.fillStyle = '#d23b3b'; g.fillRect(x - s * 0.35, y - s * 0.32, s * 0.7, s * 0.32);
    } else if (label === 'dock') {
      g.fillStyle = '#6d5a45'; g.fillRect(x - s * 1.2, y - s * 0.35, s * 2.4, s * 0.3);
      g.fillStyle = '#4a3c2e'; for (let i = -2; i <= 2; i++) g.fillRect(x + i * s * 0.5 - 2, y - s * 0.35, 4, s * 0.45);
    } else {                                      // debris / generic obstacle
      g.fillStyle = '#5b4a36'; g.beginPath(); g.ellipse(x, y - s * 0.12, s * 0.75, s * 0.22, 0.1, 0, 7); g.fill();
      g.fillStyle = '#7a6448'; g.fillRect(x - s * 0.5, y - s * 0.3, s * 0.9, s * 0.12);
    }
  }
  let camTimer = 0;
  setInterval(() => {
    if (!camEls.size || document.hidden) return;
    camTimer++;
    const fps = clamp(CAM.stream_fps, 1, 15);
    if (camTimer % Math.max(1, Math.round(15 / Math.min(fps, 6))) !== 0) return;  // ≤ 6 fps to the <img>
    const byView = {};
    camEls.forEach((el) => {
      if (!el.isConnected) { camEls.delete(el); return; }
      const v = el.__demoView || 'left';
      if (!byView[v]) byView[v] = renderFrame(v);
      imgDesc.set.call(el, byView[v]);
    });
  }, 1000 / 15);

  // ---------------------------------------- recordings: still-frame playback
  function sentryFrame(name) {
    const c = REC.clips.find((x) => x.file === name);
    const W = 640, H = 360;
    g.save(); g.fillStyle = '#101010'; g.fillRect(0, 0, W, H);
    g.strokeStyle = '#181c1e'; g.lineWidth = 1;
    for (let x = 0; x < W; x += 40) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke(); }
    for (let y = 0; y < H; y += 40) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
    g.font = '700 20px "IBM Plex Mono", monospace'; g.fillStyle = '#ffaa3c';
    g.fillText('D.R.E.A.M.S  SENTRY (SIM)', 16, 36);
    g.font = '500 15px "IBM Plex Mono", monospace'; g.fillStyle = '#78e6fa';
    const lines = ['CLIP ' + (c ? c.trigger : '—'), 'REASON ' + (c ? c.reason : '—'),
      'LAT ' + S.lat.toFixed(5), 'LON ' + S.lon.toFixed(5), 'HULL DRY'];
    lines.forEach((ln, i) => g.fillText(ln, 16, 82 + i * 30));
    g.fillStyle = '#d2e1f0'; g.font = '500 13px "IBM Plex Mono", monospace';
    g.fillText(c ? new Date(c.started * 1000).toLocaleString() : '', 16, H - 40);
    g.fillStyle = '#8592ac'; g.fillText('demo: still frame — clip playback needs the boat', 16, H - 18);
    g.restore();
    return cv.toDataURL('image/jpeg', 0.8);
  }
  const mediaDesc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
  Object.defineProperty(HTMLMediaElement.prototype, 'src', {
    configurable: true, enumerable: true,
    get() { return mediaDesc.get.call(this); },
    set(v) {
      const s = String(v); const m = s.match(/\/api\/recordings\/([^?]+)/);
      if (m) {
        this.poster = sentryFrame(decodeURIComponent(m[1]));
        this.removeAttribute('src');
        if (typeof window.toast === 'function') window.toast('Demo: showing a still — recorded clips stay on the boat', true);
        return;
      }
      mediaDesc.set.call(this, v);
    },
  });
  // DOWNLOAD builds an <a href="/api/recordings/..."> and clicks it.
  document.addEventListener('click', (e) => {
    const a = e.target && e.target.closest && e.target.closest('a[href*="/api/recordings/"]');
    if (a) { e.preventDefault(); if (typeof window.toast === 'function') window.toast('Downloads aren’t available in the demo', false); }
  }, true);

  // Basemap: the V2 page uses CARTO dark_all tiles, which now return an "API KEY
  // REQUIRED" placeholder for every referer. Swap the page's tile layer, at runtime,
  // for Esri's keyless Dark Gray Canvas (native to z16; Leaflet upscales beyond).
  document.addEventListener('DOMContentLoaded', () => {
    try {
      /* global map, L */
      if (typeof map === 'undefined' || typeof L === 'undefined') return;
      map.eachLayer((l) => {
        if (!(l instanceof L.TileLayer) || !/cartocdn/.test(l._url || '')) return;
        const old = l.getAttribution && l.getAttribution();
        if (old) map.attributionControl.removeAttribution(old);
        l.options.maxNativeZoom = 16;
        l.options.attribution = 'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors';
        map.attributionControl.addAttribution(l.options.attribution);
        l.setUrl('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}');
      });
    } catch (e) { console.warn('[demo] basemap swap failed', e); }
  });

  // Links to pages that only exist on the boat (API docs, waypoint planner).
  window.demoUnavailable = function (what) {
    if (typeof window.toast === 'function') window.toast(what + ' isn’t part of this static demo', false);
    return false;
  };
})();
