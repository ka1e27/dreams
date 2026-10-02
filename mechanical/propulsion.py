"""D.R.E.A.M.S V2 resistance, propeller and motor sizing.

Uses the hull and mass model in hull_sizing.py. Stdlib only:
    python mechanical/propulsion.py               # report
    python mechanical/propulsion.py --beam 0.1524 # same boat with 6 in hulls
    python mechanical/propulsion.py --selftest    # Michell integral vs the Wigley hull

Resistance build-up for the catamaran (both hulls):
    R = [(1+k) R_F + R_W + R_TR + R_APP + R_AIR] x (1 + service margin)
    R_F    ITTC-57 friction on the wetted surface
    R_W    Michell thin-ship wave resistance with twin-hull interference, transom treated
           as dry (open body), as Michlet does
    R_TR   Holtrop (1984) immersed-transom resistance
    R_APP  outdrive legs and lower pods (streamlined strut + pod)
    R_AIR  bridge, box and mast frontal area, still air
Propeller loading uses actuator-disk (momentum) theory with an empirical efficiency
factor for motor + belt + blade losses, calibrated to Blue Robotics' published bollard
data for the M200; the belt outdrive's bollard point is an estimate until it is tested.
Treat the output as +/- 30 % until the first hull is tow-tested.
"""

from __future__ import annotations

import argparse
import cmath
import math
from dataclasses import dataclass

from hull_sizing import (
    G,
    NU_WATER,
    RHO_WATER,
    Boat,
    Hull,
    conditions,
    draft_for,
    table,
    variant,
)

RHO_AIR = 1.2


# ---- Michell wave resistance ---------------------------------------------------------------


def _exp_moments(a: float, h: float) -> tuple[float, float]:
    """J0 = int_0^h e^{-a s} ds, J1 = int_0^h s e^{-a s} ds."""
    ah = a * h
    if ah < 1e-6:
        return h - a * h * h / 2, h * h / 2 - a * h**3 / 3
    e = math.exp(-ah)
    return (1 - e) / a, (1 - e * (1 + ah)) / (a * a)


def _depth_integral_chine(hull: Hull, x: float, t: float, a: float) -> float:
    """g(x) = int_0^T f(x, zeta) e^{-a zeta} d zeta for the hard-chine section (zeta = depth
    below the waterline), done analytically: constant half-breadth above the chine, linear
    V below it."""
    zk = hull.keel_z(x)
    zeta_k = t - zk  # keel depth below the waterline
    if zeta_k <= 0:
        return 0.0
    hb, c = hull.half_beam(x), hull.chine_rise(x)
    zeta_c = t - zk - c  # chine depth below the waterline
    if zeta_c <= 0:  # waterline below the chine: pure V, f = (zeta_k - zeta) / tan(beta)
        tb = math.tan(math.radians(hull.deadrise_deg))
        j0, j1 = _exp_moments(a, zeta_k)
        return (zeta_k * j0 - j1) / tb
    j0c, _ = _exp_moments(a, zeta_c)
    top = hb * j0c
    span = zeta_k - zeta_c
    j0, j1 = _exp_moments(a, span)
    return top + hb * math.exp(-a * zeta_c) * (span * j0 - j1) / span


def _filon(values: list[float], xs: list[float], k: float) -> complex:
    """int g(x) e^{ikx} dx for piecewise-linear g sampled at xs (exact for any k)."""
    total = 0j
    for n in range(len(xs) - 1):
        h = xs[n + 1] - xs[n]
        kh = k * h
        if abs(kh) < 1e-3:
            i0 = complex(h, k * h * h / 2)
            i1 = complex(h * h / 2, k * h**3 / 3)
        else:
            e = cmath.exp(1j * kh)
            i0 = (e - 1) / (1j * k)
            i1 = h * e / (1j * k) + (e - 1) / (k * k)
        ph = cmath.exp(1j * k * xs[n])
        total += ph * (values[n] * (i0 - i1 / h) + values[n + 1] * i1 / h)
    return total


def michell(body, t: float, speed: float, spacing: float | None = None,
            open_transom: bool = False, nx: int = 400, nu: int = 3000,
            lam_max: float = 60.0, numeric: bool = False) -> float:
    """Wave resistance (N) of one body, or of a twin-hull pair at centreline spacing."""
    k0 = G / speed**2
    xs = [body.loa * i / nx for i in range(nx + 1)]
    u_max = math.acosh(lam_max)
    du = u_max / nu
    if numeric:  # generic body: tabulate half-breadths once, piecewise-linear in depth
        nz = 48
        hz = t / nz
        zetas = [j * hz for j in range(nz + 1)]
        fgrid = [[body.half_width(x, t - zt) for zt in zetas] for x in xs]
    total = 0.0
    prev_phase = None
    for m in range(nu + 1):
        u = m * du
        lam = math.cosh(u)
        k, a = k0 * lam, k0 * lam * lam
        if numeric:
            j0, j1 = _exp_moments(a, hz)
            wts = [0.0] * (nz + 1)
            for j in range(nz):
                e = math.exp(-a * zetas[j])
                wts[j] += e * (j0 - j1 / hz)
                wts[j + 1] += e * j1 / hz
            g = [sum(fr[j] * wts[j] for j in range(nz + 1)) for fr in fgrid]
        else:
            g = [_depth_integral_chine(body, x, t, a) for x in xs]
        amp = -1j * k * _filon(g, xs, k)  # closed body: int f_x e^{..} = -ik int f e^{..}
        if open_transom:  # no closure at the transom: drop the jump term
            amp -= g[0]
        integrand = abs(amp) ** 2 * lam**2  # lam^2/sqrt(lam^2-1) d(lam) = cosh^2(u) du
        if spacing is not None:
            phase = k0 * lam * math.sqrt(max(lam * lam - 1, 0.0)) * spacing / 2
            fast = prev_phase is not None and abs(phase - prev_phase) > 1.0
            integrand *= 2.0 if fast else 4 * math.cos(phase) ** 2
            prev_phase = phase
        w = 0.5 if m in (0, nu) else 1.0
        total += w * integrand * du
    return 4 * RHO_WATER * G**2 / (math.pi * speed**2) * total


@dataclass
class Wigley:
    loa: float = 1.0
    beam: float = 0.1
    draft: float = 0.0625

    def half_width(self, x: float, z: float) -> float:
        xi, zeta = 2 * x / self.loa - 1, (self.draft - z) / self.draft
        if not (-1 <= xi <= 1 and 0 <= zeta <= 1):
            return 0.0
        return self.beam / 2 * (1 - xi * xi) * (1 - zeta * zeta)


def selftest() -> None:
    w = Wigley()
    n = 200
    area = 0.0  # wetted surface, both sides
    for i in range(n):
        for j in range(n):
            x, z = (i + 0.5) / n * w.loa, (j + 0.5) / n * w.draft
            dx, dz = 1e-5, 1e-6
            fx = (w.half_width(x + dx, z) - w.half_width(x - dx, z)) / (2 * dx)
            fz = (w.half_width(x, z + dz) - w.half_width(x, z - dz)) / (2 * dz)
            area += 2 * math.sqrt(1 + fx * fx + fz * fz) * (w.loa / n) * (w.draft / n)
    print(f"Wigley hull L=1, B/L=0.1, T/L=0.0625, wetted surface S = {area:.4f} m^2")
    print("Expect the classic Michell curve: a hump near Fn 0.3, a hollow near 0.35 and the main hump "
          "near 0.5, at a few x 10^-3 (Michell runs ~20-40 % above tank data).")
    for fn in (0.25, 0.30, 0.35, 0.40, 0.50):
        u = fn * math.sqrt(G * w.loa)
        rw = michell(w, w.draft, u, nx=200, nu=800, lam_max=30.0, numeric=True)
        print(f"  Fn {fn:.2f}: C_w x 1000 = {rw / (0.5 * RHO_WATER * u * u * area) * 1000:.2f}")


# ---- Resistance build-up -------------------------------------------------------------------

FORM_FACTOR = 1.25  # (1+k) for a demi-hull at s/L ~ 0.55, incl. viscous interference
SERVICE_MARGIN = 0.15  # weed, fouling, chop, steering
THRUST_DEDUCTION = 0.05
WAKE_FRACTION = 0.03
AIR_AREA = 0.20  # m^2, frontal: box + mast + cameras + hull topsides
AIR_CD = 1.0
APP_CD = 0.35  # outdrive leg (t/c 0.35 strut) + lower pod, on frontal area


def appendage_area(boat: Boat, draft: float) -> float:
    """Frontal area of one outdrive below the waterline: leg down to the pod, plus the pod."""
    d = boat.drive
    leg = d.leg_t * max(draft - (d.prop_z(draft) + d.pod_d / 2), 0.0)
    return leg + math.pi / 4 * d.pod_d**2


@dataclass
class Resistance:
    speed: float
    fn: float
    friction: float
    wave: float
    transom: float
    appendage: float
    air: float

    @property
    def total(self) -> float:
        bare = FORM_FACTOR * self.friction + self.wave + self.transom + self.appendage + self.air
        return bare * (1 + SERVICE_MARGIN)


def resistance(hull: Hull, boat: Boat, mass: float, speed: float) -> Resistance:
    h = draft_for(hull, mass / RHO_WATER / 2)
    s = boat.spacing(hull)
    rn = speed * h.lwl / NU_WATER
    cf = 0.075 / (math.log10(rn) - 2) ** 2
    rf = 0.5 * RHO_WATER * speed**2 * 2 * h.wsa * cf
    # Open-body (dry transom) Michell, as Michlet does for transom sterns: closing the body
    # abruptly at a blunt transom makes spurious short waves at low speed. The wet-transom
    # base drag is Holtrop's R_TR below.
    rw = michell(hull, h.draft, speed, s, open_transom=True)
    # Holtrop transom term, both hulls
    b_wl = hull.beam
    cwp = h.awp / (h.lwl * b_wl)
    fn_t = speed / math.sqrt(2 * G * h.transom_area / (b_wl + b_wl * cwp)) if h.transom_area else 99
    c6 = 0.2 * (1 - 0.2 * fn_t) if fn_t < 5 else 0.0
    rtr = 2 * 0.5 * RHO_WATER * speed**2 * h.transom_area * c6
    rapp = 2 * 0.5 * RHO_WATER * speed**2 * appendage_area(boat, h.draft) * APP_CD
    rair = 0.5 * RHO_AIR * speed**2 * AIR_AREA * AIR_CD
    return Resistance(speed, speed / math.sqrt(G * h.lwl), rf, rw, rtr, rapp, rair)


# ---- Propellers and motors -----------------------------------------------------------------


def ideal_efficiency(thrust: float, va: float, d: float) -> float:
    a = math.pi / 4 * d * d
    ct = thrust / (0.5 * RHO_WATER * va * va * a)
    return 2 / (1 + math.sqrt(1 + ct))


def ideal_bollard_power(thrust: float, d: float) -> float:
    return thrust**1.5 / math.sqrt(2 * RHO_WATER * math.pi / 4 * d * d)


@dataclass
class Propulsor:
    name: str
    d: float  # prop diameter, m
    envelope: float  # outer diameter of prop or duct, m
    bollard_n: float  # full-throttle bollard thrust, N (manufacturer, or estimate)
    bollard_w: float  # electrical power at that point, W
    kappa: float  # motor x drive x blade efficiency at cruise (the non-ideal factor)
    immersion: float  # required immersion of the envelope top below the waterline, m
    cost: str = ""  # both drives, USD, 2026


# Belt outdrive (baseline): ~380 KV 4108-size outrunner, 1:1 HTD 3M belt, 110 mm prop. Bollard
# is an estimate: 30 A motor limit -> ~0.75 N m -> ~55 N from a 110 x 75 prop (B-series K_T/K_Q).
# kappa 0.46: hobby outrunner ~0.85 x belt + wet bearings ~0.93 x blade ~0.6. Test it on the stand.
BELT_OUTDRIVE = Propulsor("Belt outdrive, 110 mm prop (baseline)", 0.110, 0.110, 55.0, 230,
                          0.46, 0.2 * 0.110, "$140-200")
# Blue Robotics published data (16 V): weedless 5.63 kgf; T200 5.25 kgf; both 390 W max.
M200_WEEDLESS = Propulsor("M200 + weedless prop (BlueBoat drive)", 0.112, 0.112, 5.63 * G, 390,
                          0.50, 0.2 * 0.112, "$390-410")
T200 = Propulsor("T200 ducted thruster", 0.076, 0.100, 5.25 * G, 390, 0.45, 0.015, "~$400")
CANDIDATES = (BELT_OUTDRIVE, M200_WEEDLESS, T200)
DRIVE_WH = 2 * 12 * 18 * 0.9  # 2x M18 HD12.0, one per VESC, 90 % usable


DRIVE_FIXED_W = 3.0  # per drive: VESC idle + motor no-load losses


def power_at(p: Propulsor, thrust: float, va: float) -> float:
    """Electrical power (W) for one propulsor delivering `thrust` at advance speed va."""
    if va < 1e-3:
        kappa_b = ideal_bollard_power(p.bollard_n, p.d) / p.bollard_w
        return ideal_bollard_power(thrust, p.d) / kappa_b
    return thrust * va / (ideal_efficiency(thrust, va, p.d) * p.kappa) + DRIVE_FIXED_W


def total_draft(p: Propulsor, draft: float) -> float:
    """Waterline to lowest point with the envelope top `immersion` below the waterline."""
    z_bottom = draft - p.immersion - p.envelope
    return draft + max(0.0, -z_bottom)


def report(hull: Hull | None = None, boat: Boat | None = None) -> None:
    hull, boat = hull or Hull(), boat or Boat()
    design = conditions(hull, boat)[1]
    h = draft_for(hull, design.total / RHO_WATER / 2)
    speeds = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
    res = [resistance(hull, boat, design.total, v) for v in speeds]

    print(f"## Resistance (design condition, {design.total:.1f} kg, {hull.beam * 1000:.0f} mm hulls, both)\n")
    rows = [[f"{r.speed:.1f}", f"{r.fn:.2f}", f"{FORM_FACTOR * r.friction:.1f}", f"{r.wave:.1f}",
             f"{r.transom:.1f}", f"{r.appendage:.1f}", f"{r.air:.1f}", f"{r.total:.1f}",
             f"{r.total / (design.total * G):.3f}"] for r in res]
    print(table(["V m/s", "Fn", "Friction x(1+k) N", "Wave N", "Transom N", "Drives N", "Air N",
                 f"Total +{SERVICE_MARGIN:.0%} N", "R/W"], rows))
    print(f"\nForm factor {FORM_FACTOR}, service margin {SERVICE_MARGIN:.0%}, design draft "
          f"{h.draft * 1000:.0f} mm, transom immersion {(h.draft - hull.stern_rise) * 1000:.0f} mm. "
          f"'Drives' is the two outdrive legs + pods ({appendage_area(boat, h.draft) * 1e4:.0f} cm^2 "
          f"frontal each, Cd {APP_CD}).")

    print("\n## Propeller diameter trade (per prop, generic open prop, kappa 0.5)\n")
    rows = []
    r15 = res[speeds.index(1.5)]
    r30 = res[speeds.index(3.0)]
    for d in (0.050, 0.060, 0.070, 0.080, 0.090, 0.100, 0.112):
        p = Propulsor("", d, d, 0, 1, 0.50, 0.2 * d)
        cells = [f"{d * 1000:.0f}"]
        for r in (r15, r30):
            thrust = r.total / 2 / (1 - THRUST_DEDUCTION)
            va = r.speed * (1 - WAKE_FRACTION)
            eta = ideal_efficiency(thrust, va, d) * p.kappa
            cells += [f"{eta:.2f}", f"{power_at(p, thrust, va):.0f}"]
        cells.append(f"{total_draft(p, h.draft) * 1000:.0f}")
        cells.append("yes" if d + 0.2 * d <= h.draft else "no")
        rows.append(cells)
    print(table(["D mm", "eta 1.5 m/s", "W 1.5 m/s", "eta 3 m/s", "W 3 m/s", "Total draft mm",
                 "Above keel line?"], rows))
    print("\nTotal draft keeps the prop tip 0.2 D below the design waterline; 'above keel line' "
          "is the Sonobot layout (whole disc above the baseline).")

    print("\n## Candidate drives (2 per boat)\n")
    rows = []
    for p in CANDIDATES:
        cells = [p.name, p.cost, f"{p.d * 1000:.0f}", f"{2 * p.bollard_n:.0f}"]
        for r in (res[speeds.index(1.0)], r15, r30):
            thrust = r.total / 2 / (1 - THRUST_DEDUCTION)
            va = r.speed * (1 - WAKE_FRACTION)
            cells.append(f"{2 * power_at(p, thrust, va):.0f}")
        p1 = 2 * power_at(p, res[speeds.index(1.0)].total / 2 / (1 - THRUST_DEDUCTION),
                          1.0 * (1 - WAKE_FRACTION))
        p15 = 2 * power_at(p, r15.total / 2 / (1 - THRUST_DEDUCTION), 1.5 * (1 - WAKE_FRACTION))
        cells += [f"{DRIVE_WH / p1:.0f} / {DRIVE_WH / p15:.0f}", f"{total_draft(p, h.draft) * 1000:.0f}"]
        rows.append(cells)
    print(table(["Drive", "Cost (2)", "Prop mm", "Bollard N (both)", "W @1.0", "W @1.5", "W @3.0",
                 "Hours @1.0 / 1.5", "Total draft mm"], rows))
    thrust3 = r30.total / 2 / (1 - THRUST_DEDUCTION)
    print(f"\nAt 3.0 m/s each drive must push {thrust3:.0f} N. Drive energy {DRIVE_WH:.0f} Wh "
          f"(2x M18 HD12.0, one per VESC, 90 % usable); electronics run from their own pack.")
    for p in CANDIDATES:
        k_b = ideal_bollard_power(p.bollard_n, p.d) / p.bollard_w
        print(f"- {p.name}: bollard kappa = {k_b:.2f} (ideal / electrical at full throttle).")
    d = boat.drive
    rpm3 = r30.speed * (1 - WAKE_FRACTION) / (0.075 * (1 - 0.40)) * 60
    torque3 = power_at(BELT_OUTDRIVE, thrust3, 3.0 * (1 - WAKE_FRACTION)) * 0.85 / (rpm3 * math.pi / 30)
    print(f"\nBelt check at 3.0 m/s: ~{rpm3:.0f} rpm and ~{torque3:.2f} N m per drive through a "
          f"{d.pulley_teeth}T HTD 3M-{d.belt_w * 1000:.0f} belt. That is near a 9 mm belt's rating on "
          f"a 20T pulley; use 15 mm if you run fast for long. Cruise (1.5 m/s) is well inside it.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="Michell check on the Wigley hull")
    ap.add_argument("--beam", type=float, help="hull beam, m (6 in = 0.1524); same bridge")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    elif args.beam:
        report(*variant(args.beam))
    else:
        report()


if __name__ == "__main__":
    main()
