# The 0.5.0 statistics simulations

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

`ttest_bootstrap_continuous.py` (first run, from the same code before it was copied here):

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

`bootstrap_skew_guard.py` (first run, from the same code before it was copied here):

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
- No test tried holds the level on a long tail of losses below 50 items; the studentized bootstrap at half the
  level does from 50 items on. RFC-015 therefore calls that case inconclusive below 50 items.
- "Long tail of losses" here is a centred lognormal with shape 1 (strongly skewed); milder skew fares better. The
  validation suite in `harness/tests/test_stats_validity.py` (RFC-015, Testing) reruns a smaller fixed grid.
