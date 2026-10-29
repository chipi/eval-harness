# The 0.7.0 statistics simulations

The evidence behind [RFC-015](../../../docs/rfc/RFC-015-noninferiority-looks-power.md): which
non-inferiority test holds its level for which measure. Every script is seeded and runs from the
repository root with the harness's Python (it imports `harness/scripts/stats.py`). The true paired
difference is exactly −margin in every case, so a valid one-sided 2.5% test rejects at most 2.5% of the
time. Monte Carlo error is about ±0.003 at 3000 runs and ±0.004 at 1500.

| script | question | runs |
| --- | --- | --- |
| `signflip_binary.py` | the shifted sign-flip test on 0/1 differences (the final statistics review's check) | 3000 |
| `tango_binary.py` | Tango's score test (1998) beside it, on a wider grid | 3000 |
| `signflip_continuous.py` | the shifted sign-flip test on continuous differences: normal, long tail of gains, long tail of losses | 2000 |
| `ttest_bootstrap_continuous.py` | the paired t-test and the studentized bootstrap on the same shapes | 1500 |
| `bootstrap_skew_guard.py` | the bootstrap at half the level when the skewness is below −1 | 1500 |

## Results (2026-10-26)

`signflip_binary.py` and `tango_binary.py` (re-run from these copies; identical to the first runs):

```text
   n  P(-1)  P(+1) margin    tango signflip
  16   0.15   0.05   0.10   0.0163   0.0777
  16    0.3    0.2   0.10   0.0163   0.0147
  24   0.15   0.05   0.10   0.0107   0.0227
  24   0.05    0.0   0.05   0.0000   0.2993
  30   0.12   0.02   0.10   0.0113   0.1073
  50   0.12   0.02   0.10   0.0143      n/a
 100   0.12   0.02   0.10   0.0243      n/a
 200   0.05    0.0   0.05   0.0103      n/a
 200   0.12   0.02   0.10   0.0230      n/a
```

`signflip_continuous.py` (re-run from this copy; identical):

```text
   n   shape  type I
  10  normal  0.0250
  10   right  0.0005
  10    left  0.1510
  20  normal  0.0320
  20   right  0.0020
  20    left  0.1420
  30  normal  0.0265
  30   right  0.0035
  30    left  0.1270
```

`ttest_bootstrap_continuous.py` (first run before it was copied here; re-run from this copy on 2026-10-26, identical):

```text
   n   shape  t-test  boot-t
  10  normal  0.0300  0.0327
  10   right  0.0007  0.0080
  10    left  0.1707  0.0847
  20  normal  0.0267  0.0313
  20   right  0.0020  0.0127
  20    left  0.1473  0.0800
  30  normal  0.0227  0.0220
  30   right  0.0040  0.0153
  30    left  0.1180  0.0673
  50  normal  0.0253  0.0280
  50   right  0.0033  0.0220
  50    left  0.0967  0.0513
 100  normal  0.0240  0.0240
 100   right  0.0033  0.0240
 100    left  0.0773  0.0500
```

`bootstrap_skew_guard.py` (first run before it was copied here; re-run from this copy on 2026-10-26, identical):

```text
   n   shape  type I  guard fired
  10    left  0.0827  0.621
  10  normal  0.0233  0.041
  20    left  0.0573  0.849
  20  normal  0.0280  0.017
  30    left  0.0480  0.930
  30  normal  0.0327  0.012
  50    left  0.0300  0.987
  50  normal  0.0287  0.002
 100    left  0.0273  0.999
 100  normal  0.0207  0.000
```

## What it shows

- The shifted sign-flip test is invalid for 0/1 measures (up to 0.299) and for continuous measures with a long
  tail of losses (up to 0.151); it is fine for symmetric continuous differences.
- Tango's score test holds the level for 0/1 measures everywhere tried (conservative at small n).
- The first skew guard (g1 < −1, α/2, inconclusive below 50 items), chosen on the shape-1 tail alone, does not
  hold across tail weights: `bootstrap_spec_check.py` runs RFC-015's exact specification (p = (1 + #{t* ≥ T})/(B + 1),
  resamples with s* = 0 dropped, B = 999) on normal differences and lognormal loss tails of σ 0.25 to 1.0:

```text
type I at the margin, nominal 0.025, 1000 simulations, B = 999
   n           shape  type I guard fired  inconclusive (guard, n<50)
  10          normal   0.023          6%                          6%
  10  lognormal 0.25   0.019         14%                         14%
  10   lognormal 0.5   0.049         32%                         32%
  10  lognormal 0.75   0.066         50%                         50%
  10   lognormal 1.0   0.075         62%                         62%
  20          normal   0.035          2%                          2%
  20  lognormal 0.25   0.034         17%                         17%
  20   lognormal 0.5   0.046         45%                         45%
  20  lognormal 0.75   0.044         71%                         71%
  20   lognormal 1.0   0.043         83%                         83%
  30          normal   0.026          1%                          1%
  30  lognormal 0.25   0.029         17%                         17%
  30   lognormal 0.5   0.022         55%                         55%
  30  lognormal 0.75   0.025         80%                         80%
  30   lognormal 1.0   0.014         94%                         94%
  50          normal   0.028          0%                          0%
  50  lognormal 0.25   0.029         18%                          0%
  50   lognormal 0.5   0.027         64%                          0%
  50  lognormal 0.75   0.034         94%                          0%
  50   lognormal 1.0   0.042         99%                          0%
 100          normal   0.029          0%                          0%
 100  lognormal 0.25   0.026         17%                          0%
 100   lognormal 0.5   0.023         82%                          0%
 100  lognormal 0.75   0.018         99%                          0%
 100   lognormal 1.0   0.023        100%                          0%
```

- `bootstrap_rule_grid.py N OUT.jsonl` records, per simulation, g1 and p at the margin (null) and at no difference
  (power), 1000 simulations per cell, for n in 10, 20, 30, 50, 100 (and 200, run to check the large-sample end).
  `bootstrap_rule_eval.py` scores candidate rules on those same draws. The raw files are not committed (about 10,000
  lines per n); the grid reproduces them from its seeds (`1000 + n`). Output for n = 10 to 100:

```text
RFC draft: g1<-1 -> a/2, n<50 inconclusive
   n           shape  error  power
  10  lognormal 0.25  0.038  0.206
  10   lognormal 0.5  0.040  0.185
  10  lognormal 0.75  0.053  0.216
  10   lognormal 1.0  0.092  0.220
  10          normal  0.015  0.204
  20  lognormal 0.25  0.035  0.344
  20   lognormal 0.5  0.034  0.260
  20  lognormal 0.75  0.033  0.198
  20   lognormal 1.0  0.042  0.114
  20          normal  0.036  0.387
  30  lognormal 0.25  0.029  0.451
  30   lognormal 0.5  0.024  0.282
  30  lognormal 0.75  0.029  0.139
  30   lognormal 1.0  0.018  0.061
  30          normal  0.015  0.555
  50  lognormal 0.25  0.024  0.692
  50   lognormal 0.5  0.021  0.548
  50  lognormal 0.75  0.028  0.532
  50   lognormal 1.0  0.038  0.490
  50          normal  0.016  0.804
 100  lognormal 0.25  0.028  0.941
 100   lognormal 0.5  0.022  0.850
 100  lognormal 0.75  0.025  0.753
 100   lognormal 1.0  0.019  0.686
 100          normal  0.019  0.980
worst error 0.092

CHOSEN: g1<-0.5 -> n<50 inc, a/4 below 100, a/2 from 100; any n<30 inc
   n           shape  error  power
  10  lognormal 0.25  0.000  0.000
  10   lognormal 0.5  0.000  0.000
  10  lognormal 0.75  0.000  0.000
  10   lognormal 1.0  0.000  0.000
  10          normal  0.000  0.000
  20  lognormal 0.25  0.000  0.000
  20   lognormal 0.5  0.000  0.000
  20  lognormal 0.75  0.000  0.000
  20   lognormal 1.0  0.000  0.000
  20          normal  0.000  0.000
  30  lognormal 0.25  0.016  0.275
  30   lognormal 0.5  0.007  0.086
  30  lognormal 0.75  0.005  0.018
  30   lognormal 1.0  0.000  0.004
  30          normal  0.014  0.525
  50  lognormal 0.25  0.013  0.570
  50   lognormal 0.5  0.009  0.415
  50  lognormal 0.75  0.017  0.424
  50   lognormal 1.0  0.025  0.407
  50          normal  0.016  0.785
 100  lognormal 0.25  0.026  0.917
 100   lognormal 0.5  0.015  0.848
 100  lognormal 0.75  0.023  0.753
 100   lognormal 1.0  0.019  0.686
 100          normal  0.019  0.980
worst error 0.026

g1<-0.5 -> a/2, n<50 inconclusive
   n           shape  error  power
  10  lognormal 0.25  0.037  0.168
  10   lognormal 0.5  0.035  0.132
  10  lognormal 0.75  0.041  0.134
  10   lognormal 1.0  0.066  0.114
  10          normal  0.014  0.189
  20  lognormal 0.25  0.027  0.258
  20   lognormal 0.5  0.019  0.133
  20  lognormal 0.75  0.016  0.065
  20   lognormal 1.0  0.007  0.023
  20          normal  0.036  0.352
  30  lognormal 0.25  0.016  0.275
  30   lognormal 0.5  0.007  0.086
  30  lognormal 0.75  0.005  0.018
  30   lognormal 1.0  0.000  0.004
  30          normal  0.014  0.525
  50  lognormal 0.25  0.016  0.640
  50   lognormal 0.5  0.016  0.525
  50  lognormal 0.75  0.024  0.530
  50   lognormal 1.0  0.036  0.489
  50          normal  0.016  0.793
 100  lognormal 0.25  0.026  0.917
 100   lognormal 0.5  0.015  0.848
 100  lognormal 0.75  0.023  0.753
 100   lognormal 1.0  0.019  0.686
 100          normal  0.019  0.980
worst error 0.066

g1<-0.5 -> a/2, n<50 inc; any n<30 inc
   n           shape  error  power
  10  lognormal 0.25  0.000  0.000
  10   lognormal 0.5  0.000  0.000
  10  lognormal 0.75  0.000  0.000
  10   lognormal 1.0  0.000  0.000
  10          normal  0.000  0.000
  20  lognormal 0.25  0.000  0.000
  20   lognormal 0.5  0.000  0.000
  20  lognormal 0.75  0.000  0.000
  20   lognormal 1.0  0.000  0.000
  20          normal  0.000  0.000
  30  lognormal 0.25  0.016  0.275
  30   lognormal 0.5  0.007  0.086
  30  lognormal 0.75  0.005  0.018
  30   lognormal 1.0  0.000  0.004
  30          normal  0.014  0.525
  50  lognormal 0.25  0.016  0.640
  50   lognormal 0.5  0.016  0.525
  50  lognormal 0.75  0.024  0.530
  50   lognormal 1.0  0.036  0.489
  50          normal  0.016  0.793
 100  lognormal 0.25  0.026  0.917
 100   lognormal 0.5  0.015  0.848
 100  lognormal 0.75  0.023  0.753
 100   lognormal 1.0  0.019  0.686
 100          normal  0.019  0.980
worst error 0.036

g1<-0.5 -> a/4, n<50 inc; any n<30 inc
   n           shape  error  power
  10  lognormal 0.25  0.000  0.000
  10   lognormal 0.5  0.000  0.000
  10  lognormal 0.75  0.000  0.000
  10   lognormal 1.0  0.000  0.000
  10          normal  0.000  0.000
  20  lognormal 0.25  0.000  0.000
  20   lognormal 0.5  0.000  0.000
  20  lognormal 0.75  0.000  0.000
  20   lognormal 1.0  0.000  0.000
  20          normal  0.000  0.000
  30  lognormal 0.25  0.016  0.275
  30   lognormal 0.5  0.007  0.086
  30  lognormal 0.75  0.005  0.018
  30   lognormal 1.0  0.000  0.004
  30          normal  0.014  0.525
  50  lognormal 0.25  0.013  0.570
  50   lognormal 0.5  0.009  0.415
  50  lognormal 0.75  0.017  0.424
  50   lognormal 1.0  0.025  0.407
  50          normal  0.016  0.785
 100  lognormal 0.25  0.019  0.876
 100   lognormal 0.5  0.008  0.778
 100  lognormal 0.75  0.014  0.683
 100   lognormal 1.0  0.008  0.621
 100          normal  0.019  0.980
worst error 0.025

g1<-0.25 -> a/2, n<50 inc; any n<30 inc
   n           shape  error  power
  10  lognormal 0.25  0.000  0.000
  10   lognormal 0.5  0.000  0.000
  10  lognormal 0.75  0.000  0.000
  10   lognormal 1.0  0.000  0.000
  10          normal  0.000  0.000
  20  lognormal 0.25  0.000  0.000
  20   lognormal 0.5  0.000  0.000
  20  lognormal 0.75  0.000  0.000
  20   lognormal 1.0  0.000  0.000
  20          normal  0.000  0.000
  30  lognormal 0.25  0.013  0.144
  30   lognormal 0.5  0.001  0.032
  30  lognormal 0.75  0.001  0.004
  30   lognormal 1.0  0.000  0.001
  30          normal  0.014  0.438
  50  lognormal 0.25  0.013  0.617
  50   lognormal 0.5  0.016  0.524
  50  lognormal 0.75  0.024  0.530
  50   lognormal 1.0  0.036  0.489
  50          normal  0.015  0.778
 100  lognormal 0.25  0.021  0.911
 100   lognormal 0.5  0.015  0.848
 100  lognormal 0.75  0.023  0.753
 100   lognormal 1.0  0.019  0.686
 100          normal  0.017  0.977
worst error 0.036

g1<-0.5 -> a/2, n<100 inc; any n<30 inc
   n           shape  error  power
  10  lognormal 0.25  0.000  0.000
  10   lognormal 0.5  0.000  0.000
  10  lognormal 0.75  0.000  0.000
  10   lognormal 1.0  0.000  0.000
  10          normal  0.000  0.000
  20  lognormal 0.25  0.000  0.000
  20   lognormal 0.5  0.000  0.000
  20  lognormal 0.75  0.000  0.000
  20   lognormal 1.0  0.000  0.000
  20          normal  0.000  0.000
  30  lognormal 0.25  0.016  0.275
  30   lognormal 0.5  0.007  0.086
  30  lognormal 0.75  0.005  0.018
  30   lognormal 1.0  0.000  0.004
  30          normal  0.014  0.525
  50  lognormal 0.25  0.012  0.313
  50   lognormal 0.5  0.004  0.036
  50  lognormal 0.75  0.000  0.006
  50   lognormal 1.0  0.000  0.000
  50          normal  0.015  0.754
 100  lognormal 0.25  0.026  0.917
 100   lognormal 0.5  0.015  0.848
 100  lognormal 0.75  0.023  0.753
 100   lognormal 1.0  0.019  0.686
 100          normal  0.019  0.980
worst error 0.026

g1<-0.5 -> a/2, no skew floor; any n<30 inc
   n           shape  error  power
  10  lognormal 0.25  0.000  0.000
  10   lognormal 0.5  0.000  0.000
  10  lognormal 0.75  0.000  0.000
  10   lognormal 1.0  0.000  0.000
  10          normal  0.000  0.000
  20  lognormal 0.25  0.000  0.000
  20   lognormal 0.5  0.000  0.000
  20  lognormal 0.75  0.000  0.000
  20   lognormal 1.0  0.000  0.000
  20          normal  0.000  0.000
  30  lognormal 0.25  0.021  0.427
  30   lognormal 0.5  0.021  0.338
  30  lognormal 0.75  0.030  0.337
  30   lognormal 1.0  0.039  0.351
  30          normal  0.015  0.546
  50  lognormal 0.25  0.016  0.640
  50   lognormal 0.5  0.016  0.525
  50  lognormal 0.75  0.024  0.530
  50   lognormal 1.0  0.036  0.489
  50          normal  0.016  0.793
 100  lognormal 0.25  0.026  0.917
 100   lognormal 0.5  0.015  0.848
 100  lognormal 0.75  0.023  0.753
 100   lognormal 1.0  0.019  0.686
 100          normal  0.019  0.980
worst error 0.039

always a/2, any n<30 inc
   n           shape  error  power
  10  lognormal 0.25  0.000  0.000
  10   lognormal 0.5  0.000  0.000
  10  lognormal 0.75  0.000  0.000
  10   lognormal 1.0  0.000  0.000
  10          normal  0.000  0.000
  20  lognormal 0.25  0.000  0.000
  20   lognormal 0.5  0.000  0.000
  20  lognormal 0.75  0.000  0.000
  20   lognormal 1.0  0.000  0.000
  20          normal  0.000  0.000
  30  lognormal 0.25  0.017  0.383
  30   lognormal 0.5  0.017  0.325
  30  lognormal 0.75  0.027  0.335
  30   lognormal 1.0  0.039  0.351
  30          normal  0.006  0.419
  50  lognormal 0.25  0.011  0.599
  50   lognormal 0.5  0.016  0.524
  50  lognormal 0.75  0.024  0.530
  50   lognormal 1.0  0.036  0.489
  50          normal  0.007  0.688
 100  lognormal 0.25  0.020  0.910
 100   lognormal 0.5  0.015  0.848
 100  lognormal 0.75  0.023  0.753
 100   lognormal 1.0  0.019  0.686
 100          normal  0.010  0.951
worst error 0.039
```

- The rule marked CHOSEN at n = 200 (`bootstrap_rule_eval.py` on the n = 200 file alone):

```text
   n           shape  error  power
 200  lognormal 0.25  0.013  0.999
 200   lognormal 0.5  0.012  0.992
 200  lognormal 0.75  0.011  0.967
 200   lognormal 1.0  0.019  0.917
 200          normal  0.023  1.000
worst error 0.023
```

- The first version of RFC-015 adopted the rule marked CHOSEN (below 30 items no continuous non-inferiority test;
  when g1 < −0.5, inconclusive below 50 items, α/4 from 50 to 99, α/2 from 100; worst error 0.026). Revision 2
  (2026-10-27) replaced it with one rule a reader can apply without a skewness threshold tuned on these shapes: the
  bootstrap-t at half the level, from 100 items, inconclusive below. On the same simulations, n = 10 to 200:

```text
ADOPTED (revision 2): always a/2, any n<100 inc
   n           shape  error  power
  10  lognormal 0.25  0.000  0.000
  10   lognormal 0.5  0.000  0.000
  10  lognormal 0.75  0.000  0.000
  10   lognormal 1.0  0.000  0.000
  10          normal  0.000  0.000
  20  lognormal 0.25  0.000  0.000
  20   lognormal 0.5  0.000  0.000
  20  lognormal 0.75  0.000  0.000
  20   lognormal 1.0  0.000  0.000
  20          normal  0.000  0.000
  30  lognormal 0.25  0.000  0.000
  30   lognormal 0.5  0.000  0.000
  30  lognormal 0.75  0.000  0.000
  30   lognormal 1.0  0.000  0.000
  30          normal  0.000  0.000
  50  lognormal 0.25  0.000  0.000
  50   lognormal 0.5  0.000  0.000
  50  lognormal 0.75  0.000  0.000
  50   lognormal 1.0  0.000  0.000
  50          normal  0.000  0.000
 100  lognormal 0.25  0.020  0.910
 100   lognormal 0.5  0.015  0.848
 100  lognormal 0.75  0.023  0.753
 100   lognormal 1.0  0.019  0.686
 100          normal  0.010  0.951
 200  lognormal 0.25  0.012  0.999
 200   lognormal 0.5  0.012  0.992
 200  lognormal 0.75  0.011  0.967
 200   lognormal 1.0  0.019  0.917
 200          normal  0.012  1.000
worst error 0.023
```

- The validation suite in `harness/tests/test_stats_validity.py` (RFC-015, Testing) reruns a smaller fixed grid.
