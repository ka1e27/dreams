## Resistance (design condition, 34.3 kg, 220 mm hulls, both)

| V m/s | Fn | Friction x(1+k) N | Wave N | Transom N | Drives N | Air N | Total +15% N | R/W |
|---|---|---|---|---|---|---|---|---|
| 0.5 | 0.14 | 0.6 | 0.0 | 0.4 | 0.2 | 0.0 | 1.5 | 0.004 |
| 1.0 | 0.28 | 2.1 | 1.2 | 1.4 | 0.9 | 0.1 | 6.6 | 0.020 |
| 1.5 | 0.42 | 4.4 | 9.6 | 2.5 | 2.0 | 0.3 | 21.5 | 0.064 |
| 2.0 | 0.56 | 7.4 | 15.5 | 3.3 | 3.5 | 0.5 | 34.7 | 0.103 |
| 2.5 | 0.70 | 11.0 | 16.2 | 3.4 | 5.5 | 0.8 | 42.4 | 0.126 |
| 3.0 | 0.84 | 15.3 | 16.3 | 2.3 | 7.9 | 1.1 | 49.4 | 0.147 |

Form factor 1.25, service margin 15%, design draft 99 mm, transom immersion 59 mm. 'Drives' is the two outdrive legs + pods (25 cm^2 frontal each, Cd 0.35).

## Propeller diameter trade (per prop, generic open prop, kappa 0.5)

| D mm | eta 1.5 m/s | W 1.5 m/s | eta 3 m/s | W 3 m/s | Total draft mm | Above keel line? |
|---|---|---|---|---|---|---|
| 50 | 0.28 | 61 | 0.33 | 232 | 99 | yes |
| 60 | 0.31 | 56 | 0.36 | 213 | 99 | yes |
| 70 | 0.34 | 52 | 0.38 | 200 | 99 | yes |
| 80 | 0.36 | 49 | 0.40 | 191 | 99 | yes |
| 90 | 0.38 | 47 | 0.42 | 185 | 108 | no |
| 100 | 0.39 | 45 | 0.43 | 180 | 120 | no |
| 112 | 0.41 | 43 | 0.44 | 175 | 134 | no |

Total draft keeps the prop tip 0.2 D below the design waterline; 'above keel line' is the Sonobot layout (whole disc above the baseline).

## Candidate drives (2 per boat)

| Drive | Cost (2) | Prop mm | Bollard N (both) | W @1.0 | W @1.5 | W @3.0 | Hours @1.0 / 1.5 | Total draft mm |
|---|---|---|---|---|---|---|---|---|
| Belt outdrive, 110 mm prop (baseline) | $140-200 | 110 | 110 | 23 | 94 | 381 | 17 / 4 | 132 |
| M200 + weedless prop (BlueBoat drive) | $390-410 | 112 | 110 | 22 | 87 | 350 | 18 / 5 | 134 |
| T200 ducted thruster | ~$400 | 76 | 103 | 26 | 110 | 432 | 16 / 4 | 115 |

At 3.0 m/s each drive must push 26 N. Drive energy 400 Wh (one 12S ~10 Ah pack for both VESCs, 90 % usable); electronics run from their own pack.
- Belt outdrive, 110 mm prop (baseline): bollard kappa = 0.41 (ideal / electrical at full throttle).
- M200 + weedless prop (BlueBoat drive): bollard kappa = 0.24 (ideal / electrical at full throttle).
- T200 ducted thruster: bollard kappa = 0.31 (ideal / electrical at full throttle).

Belt check at 3.0 m/s: ~3880 rpm and ~0.40 N m per drive through a 20T HTD 3M-9 belt. That is near a 9 mm belt's rating on a 20T pulley; use 15 mm if you run fast for long. Cruise (1.5 m/s) is well inside it.
