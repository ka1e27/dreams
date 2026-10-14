## Resistance (design condition, 31.2 kg, 220 mm hulls, both)

| V m/s | Fn | Friction x(1+k) N | Wave N | Transom N | Drives N | Air N | Total +15% N | R/W |
|---|---|---|---|---|---|---|---|---|
| 0.5 | 0.16 | 0.5 | 0.0 | 0.6 | 0.2 | 0.0 | 1.7 | 0.005 |
| 1.0 | 0.33 | 1.9 | 2.2 | 2.1 | 0.9 | 0.1 | 8.3 | 0.027 |
| 1.5 | 0.49 | 3.8 | 17.4 | 4.0 | 2.0 | 0.3 | 31.6 | 0.103 |
| 2.0 | 0.66 | 6.4 | 20.6 | 5.7 | 3.5 | 0.5 | 42.3 | 0.138 |
| 2.5 | 0.82 | 9.6 | 20.0 | 6.8 | 5.5 | 0.8 | 49.1 | 0.161 |
| 3.0 | 0.99 | 13.3 | 19.1 | 6.8 | 7.9 | 1.1 | 55.5 | 0.182 |

Form factor 1.25, service margin 15%, design draft 118 mm, transom immersion 78 mm. 'Drives' is the two outdrive legs + pods (25 cm^2 frontal each, Cd 0.35).

## Propeller diameter trade (per prop, generic open prop, kappa 0.5)

| D mm | eta 1.5 m/s | W 1.5 m/s | eta 3 m/s | W 3 m/s | Total draft mm | Above keel line? |
|---|---|---|---|---|---|---|
| 50 | 0.25 | 100 | 0.32 | 269 | 118 | yes |
| 60 | 0.28 | 89 | 0.35 | 246 | 118 | yes |
| 70 | 0.31 | 82 | 0.37 | 230 | 118 | yes |
| 80 | 0.33 | 76 | 0.39 | 219 | 118 | yes |
| 90 | 0.35 | 72 | 0.41 | 211 | 118 | yes |
| 100 | 0.37 | 69 | 0.42 | 205 | 120 | no |
| 112 | 0.38 | 66 | 0.43 | 199 | 134 | no |

Total draft keeps the prop tip 0.2 D below the design waterline; 'above keel line' is the Sonobot layout (whole disc above the baseline).

## Candidate drives (2 per boat)

| Drive | Prop mm | Bollard N (both) | W @1.0 | W @1.5 | W @3.0 | Hours @1.0 / 1.5 | Total draft mm |
|---|---|---|---|---|---|---|---|
| Belt outdrive, 110 mm prop (baseline) | 110 | 110 | 28 | 144 | 434 | 14 / 3 | 132 |
| M200 + weedless prop (BlueBoat drive) | 112 | 110 | 26 | 132 | 398 | 15 / 3 | 134 |
| T200 ducted thruster | 76 | 103 | 32 | 174 | 495 | 13 / 2 | 118 |

At 3.0 m/s each drive must push 29 N. Drive energy 400 Wh (one 12S ~10 Ah pack for both VESCs, 90 % usable); electronics run from their own pack.
- Belt outdrive, 110 mm prop (baseline): bollard kappa = 0.41 (ideal / electrical at full throttle).
- M200 + weedless prop (BlueBoat drive): bollard kappa = 0.24 (ideal / electrical at full throttle).
- T200 ducted thruster: bollard kappa = 0.31 (ideal / electrical at full throttle).

Belt check at 3.0 m/s: ~3880 rpm and ~0.45 N m per drive through a 20T HTD 3M-9 belt. That is near a 9 mm belt's rating on a 20T pulley; use 15 mm if you run fast for long. Cruise (1.5 m/s) is well inside it.
