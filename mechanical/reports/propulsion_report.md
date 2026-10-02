## Resistance (design condition, 32.0 kg, 220 mm hulls, both)

| V m/s | Fn | Friction x(1+k) N | Wave N | Transom N | Drives N | Air N | Total +15% N | R/W |
|---|---|---|---|---|---|---|---|---|
| 0.5 | 0.14 | 0.6 | 0.0 | 0.4 | 0.2 | 0.0 | 1.4 | 0.005 |
| 1.0 | 0.28 | 2.1 | 1.3 | 1.2 | 0.9 | 0.1 | 6.4 | 0.020 |
| 1.5 | 0.42 | 4.3 | 9.2 | 2.1 | 2.0 | 0.3 | 20.5 | 0.065 |
| 2.0 | 0.56 | 7.1 | 14.8 | 2.7 | 3.5 | 0.5 | 32.9 | 0.105 |
| 2.5 | 0.70 | 10.7 | 15.5 | 2.6 | 5.5 | 0.8 | 40.2 | 0.128 |
| 3.0 | 0.84 | 14.8 | 15.6 | 1.3 | 7.9 | 1.1 | 46.8 | 0.149 |

Form factor 1.25, service margin 15%, design draft 94 mm, transom immersion 54 mm. 'Drives' is the two outdrive legs + pods (25 cm^2 frontal each, Cd 0.35).

## Propeller diameter trade (per prop, generic open prop, kappa 0.5)

| D mm | eta 1.5 m/s | W 1.5 m/s | eta 3 m/s | W 3 m/s | Total draft mm | Above keel line? |
|---|---|---|---|---|---|---|
| 50 | 0.29 | 58 | 0.33 | 217 | 94 | yes |
| 60 | 0.32 | 52 | 0.36 | 200 | 94 | yes |
| 70 | 0.34 | 49 | 0.39 | 188 | 94 | yes |
| 80 | 0.36 | 46 | 0.41 | 180 | 96 | no |
| 90 | 0.38 | 44 | 0.42 | 174 | 108 | no |
| 100 | 0.40 | 43 | 0.43 | 169 | 120 | no |
| 112 | 0.41 | 41 | 0.44 | 165 | 134 | no |

Total draft keeps the prop tip 0.2 D below the design waterline; 'above keel line' is the Sonobot layout (whole disc above the baseline).

## Candidate drives (2 per boat)

| Drive | Cost (2) | Prop mm | Bollard N (both) | W @1.0 | W @1.5 | W @3.0 | Hours @1.0 / 1.5 | Total draft mm |
|---|---|---|---|---|---|---|---|---|
| Belt outdrive, 110 mm prop (baseline) | $140-200 | 110 | 110 | 22 | 89 | 359 | 17 / 4 | 132 |
| M200 + weedless prop (BlueBoat drive) | $390-410 | 112 | 110 | 21 | 82 | 330 | 18 / 5 | 134 |
| T200 ducted thruster | ~$400 | 76 | 103 | 25 | 104 | 406 | 16 / 4 | 115 |

At 3.0 m/s each drive must push 25 N. Drive energy 389 Wh (2x M18 HD12.0, one per VESC, 90 % usable); electronics run from their own pack.
- Belt outdrive, 110 mm prop (baseline): bollard kappa = 0.41 (ideal / electrical at full throttle).
- M200 + weedless prop (BlueBoat drive): bollard kappa = 0.24 (ideal / electrical at full throttle).
- T200 ducted thruster: bollard kappa = 0.31 (ideal / electrical at full throttle).

Belt check at 3.0 m/s: ~3880 rpm and ~0.38 N m per drive through a 20T HTD 3M-9 belt. That is near a 9 mm belt's rating on a 20T pulley; use 15 mm if you run fast for long. Cruise (1.5 m/s) is well inside it.
