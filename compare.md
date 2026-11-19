# Alvheim fixed-bookings runs (TEST, model 01a1e49f)

> **Errata (2026-11-18; see [ISSUES.md](ISSUES.md)).** The volumes integrate instantaneous rates and ignore downtime, so they are 5–7 % high: M BASE is 20.655 MSm3 full life by GAP CumOil (A1). The Q single-lift rows inherit Q BASE's first-step Tyrving violation (A2); monthly single lifts are running. The remaining deltas are fine to compare within this table.

Snapshot 2026-11-17 08:22. Volumes in MSm3 oil; rates piecewise-constant per step.

## Status and timing

| case | VM | status | steps | setup min | OPENFILE→1st step min | median step s | run h |
|---|---|---|---|---|---|---|---|
| H BASE | D2ads | Completed | 37 | 4.2 | 2.1 | 103 | 2.29 |
| H LIFT | D2ads | Completed | 37 | 4.3 | 2.1 | 91 | 1.68 |
| M BASE | D4ads | Completed | 174 | 23.9 | 22.0 | 88 | 7.23 |
| M LIFT | D4ads | Completed | 174 | 2.3 | 0.6 | 77 | 5.96 |
| Q BASE | D2ads | Completed | 63 | 60.3 | 13.8 | 98 | 3.95 |
| Q LIFT | D2ads | Completed | 63 | 2.9 | 0.9 | 109 | 3.22 |
| Q LIFT Boyla+Frosk | D2ads | Completed | 63 | 2.9 | 0.7 | 106 | 3.16 |
| Q LIFT Tyrving | D2ads | Completed | 63 | 51.2 | 13.8 | 138 | 3.94 |
| Q LIFT Vilje+Skogul | D2ads | Completed | 63 | 28.7 | 25.6 | 113 | 3.75 |
| Q LIFT Volund | D2ads | Completed | 63 | 2.8 | 0.8 | 111 | 3.91 |
| QY BASE | D2ads | Completed | 25 | 3.1 | 0.7 | 121 | 1.51 |
| QY LIFT | D2ads | Completed | 25 | 3.1 | 1.0 | 92 | 1.01 |
| Y BASE | D2ads | Completed | 23 | 3.0 | 0.7 | 240 | 1.65 |
| Y LIFT | D2ads | Completed | 23 | 3.2 | 0.9 | 73 | 0.89 |

## Lifting all bookings (BASE → LIFT, same grid)

| comparison | horizon | FPSO base | FPSO other | delta | delta % | B+F | Volund | V+S | Tyrving |
|---|---|---|---|---|---|---|---|---|---|
| M BASE→LIFT booking period | 2026-07→2027-10 | 3.248 | 3.442 | +0.194 | +5.97 | +0.008 | +0.037 | +0.024 | +0.157 |
| M BASE→LIFT full | 2026-07→2041-01 | 22.095 | 22.089 | -0.006 | -0.03 | +0.025 | +0.054 | +0.068 | +0.030 |
| Q BASE→LIFT booking period | 2026-07→2027-10 | 3.231 | 3.492 | +0.261 | +8.08 | +0.011 | +0.040 | +0.032 | +0.036 |
| Q BASE→LIFT full | 2026-07→2041-01 | 21.943 | 22.205 | +0.262 | +1.19 | +0.029 | +0.053 | +0.065 | +0.015 |
| QY BASE→LIFT booking period | 2026-07→2027-10 | 3.231 | 3.492 | +0.261 | +8.08 | +0.011 | +0.040 | +0.032 | +0.036 |
| QY BASE→LIFT full | 2026-07→2041-01 | 22.394 | 22.602 | +0.207 | +0.93 | +0.023 | +0.042 | -0.041 | +0.050 |
| H BASE→LIFT booking period | 2026-07→2027-10 | 3.247 | 3.540 | +0.294 | +9.04 | +0.021 | +0.041 | +0.040 | +0.052 |
| H BASE→LIFT full | 2026-07→2041-01 | 22.133 | 22.412 | +0.278 | +1.26 | +0.019 | +0.042 | +0.030 | +0.035 |
| Y BASE→LIFT booking period | 2026-07→2027-10 | 3.257 | 3.570 | +0.313 | +9.61 | +0.014 | +0.042 | +0.043 | +0.061 |
| Y BASE→LIFT full | 2026-07→2041-01 | 22.383 | 22.682 | +0.299 | +1.34 | +0.026 | +0.062 | +0.043 | +0.014 |

## Lifting one tie-in's bookings (Q grid, vs Q BASE)

| comparison | horizon | FPSO base | FPSO other | delta | delta % | B+F | Volund | V+S | Tyrving |
|---|---|---|---|---|---|---|---|---|---|
| Q BASE→LIFT Boyla+Frosk booking period | 2026-07→2027-10 | 3.231 | 3.267 | +0.035 | +1.10 | +0.021 | +0.001 | +0.008 | +0.001 |
| Q BASE→LIFT Boyla+Frosk full | 2026-07→2041-01 | 21.943 | 21.959 | +0.016 | +0.07 | +0.036 | -0.004 | -0.015 | +0.003 |
| Q BASE→LIFT Volund booking period | 2026-07→2027-10 | 3.231 | 3.248 | +0.017 | +0.52 | +0.004 | +0.037 | -0.002 | +0.002 |
| Q BASE→LIFT Volund full | 2026-07→2041-01 | 21.943 | 21.925 | -0.018 | -0.08 | +0.006 | +0.064 | -0.015 | -0.004 |
| Q BASE→LIFT Vilje+Skogul booking period | 2026-07→2027-10 | 3.231 | 3.241 | +0.010 | +0.31 | +0.001 | -0.000 | +0.011 | -0.002 |
| Q BASE→LIFT Vilje+Skogul full | 2026-07→2041-01 | 21.943 | 21.841 | -0.103 | -0.47 | +0.002 | -0.016 | +0.059 | +0.005 |
| Q BASE→LIFT Tyrving booking period | 2026-07→2027-10 | 3.231 | 3.392 | +0.160 | +4.96 | -0.014 | +0.002 | -0.004 | +0.036 |
| Q BASE→LIFT Tyrving full | 2026-07→2041-01 | 21.943 | 22.210 | +0.266 | +1.21 | +0.000 | -0.004 | -0.020 | +0.008 |

## Coarse grid accuracy (monthly REF → coarse grid, same bookings)

| comparison | horizon | FPSO base | FPSO other | delta | delta % | B+F | Volund | V+S | Tyrving |
|---|---|---|---|---|---|---|---|---|---|
| M BASE→Q BASE | 2026-07→2041-01 | 22.095 | 21.943 | -0.152 | -0.69 | +0.005 | +0.005 | +0.014 | +0.032 |
| M LIFT→Q LIFT | 2026-07→2041-01 | 22.089 | 22.205 | +0.116 | +0.53 | +0.008 | +0.004 | +0.012 | +0.017 |
| M BASE→QY BASE | 2026-07→2041-01 | 22.095 | 22.394 | +0.299 | +1.35 | +0.040 | -0.007 | +0.022 | +0.094 |
| M LIFT→QY LIFT | 2026-07→2041-01 | 22.089 | 22.602 | +0.513 | +2.32 | +0.037 | -0.019 | -0.087 | +0.115 |
| M BASE→H BASE | 2026-07→2041-01 | 22.095 | 22.133 | +0.038 | +0.17 | +0.023 | +0.009 | +0.027 | +0.048 |
| M LIFT→H LIFT | 2026-07→2041-01 | 22.089 | 22.412 | +0.323 | +1.46 | +0.017 | -0.003 | -0.011 | +0.053 |
| M BASE→Y BASE | 2026-07→2041-01 | 22.095 | 22.383 | +0.287 | +1.30 | +0.044 | -0.002 | +0.050 | +0.098 |
| M LIFT→Y LIFT | 2026-07→2041-01 | 22.089 | 22.682 | +0.593 | +2.68 | +0.045 | +0.006 | +0.025 | +0.083 |

## Coarse grid accuracy in the booking period (monthly REF → coarse grid)

| comparison | horizon | FPSO base | FPSO other | delta | delta % | B+F | Volund | V+S | Tyrving |
|---|---|---|---|---|---|---|---|---|---|
| M BASE→Q BASE | 2026-07→2027-10 | 3.248 | 3.231 | -0.017 | -0.52 | +0.008 | -0.001 | -0.005 | +0.137 |
| M LIFT→Q LIFT | 2026-07→2027-10 | 3.442 | 3.492 | +0.050 | +1.46 | +0.011 | +0.002 | +0.003 | +0.016 |
| M BASE→QY BASE | 2026-07→2027-10 | 3.248 | 3.231 | -0.017 | -0.52 | +0.008 | -0.001 | -0.005 | +0.137 |
| M LIFT→QY LIFT | 2026-07→2027-10 | 3.442 | 3.492 | +0.050 | +1.46 | +0.011 | +0.002 | +0.003 | +0.016 |
| M BASE→H BASE | 2026-07→2027-10 | 3.248 | 3.247 | -0.001 | -0.04 | +0.007 | -0.000 | -0.011 | +0.135 |
| M LIFT→H LIFT | 2026-07→2027-10 | 3.442 | 3.540 | +0.098 | +2.86 | +0.019 | +0.004 | +0.005 | +0.030 |
| M BASE→Y BASE | 2026-07→2027-10 | 3.248 | 3.257 | +0.009 | +0.28 | +0.018 | +0.001 | -0.013 | +0.136 |
| M LIFT→Y LIFT | 2026-07→2027-10 | 3.442 | 3.570 | +0.128 | +3.73 | +0.024 | +0.006 | +0.007 | +0.040 |

## Coarser grids vs quarterly Q (full horizon, same bookings)

| comparison | horizon | FPSO base | FPSO other | delta | delta % | B+F | Volund | V+S | Tyrving |
|---|---|---|---|---|---|---|---|---|---|
| Q BASE→QY BASE | 2026-07→2041-01 | 21.943 | 22.394 | +0.451 | +2.05 | +0.035 | -0.012 | +0.008 | +0.062 |
| Q LIFT→QY LIFT | 2026-07→2041-01 | 22.205 | 22.602 | +0.396 | +1.78 | +0.029 | -0.023 | -0.099 | +0.098 |
| Q BASE→H BASE | 2026-07→2041-01 | 21.943 | 22.133 | +0.190 | +0.87 | +0.019 | +0.004 | +0.012 | +0.016 |
| Q LIFT→H LIFT | 2026-07→2041-01 | 22.205 | 22.412 | +0.206 | +0.93 | +0.008 | -0.007 | -0.023 | +0.035 |
| Q BASE→Y BASE | 2026-07→2041-01 | 21.943 | 22.383 | +0.439 | +2.00 | +0.040 | -0.007 | +0.035 | +0.066 |
| Q LIFT→Y LIFT | 2026-07→2041-01 | 22.205 | 22.682 | +0.476 | +2.14 | +0.036 | +0.002 | +0.014 | +0.065 |
