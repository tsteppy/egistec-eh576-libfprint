/* Unit test for the blank-frame gate (driver/egis_blank.h).
 *
 * Raw frames are biometrics and are not in this repository, so this test runs
 * on synthetic frames and checks the property the gate depends on: a frame
 * with no finger on the sensor is the fixed pattern and nothing else, so it
 * correlates near 1 with a no-finger reference, while a frame with ridges in
 * it does not. tools/blank_gate_check.py checks the same thing on real
 * captures.
 *
 *   cc -O2 -Idriver tools/blank_gate_test.c -o /tmp/blank_gate_test -lm
 */
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <stdint.h>
#include "egis_blank.h"

#define W 70
#define H 57
#define N (W * H)

static unsigned seed = 1;
static double
rnd (void)                      /* deterministic, so the test is reproducible */
{
  seed = seed * 1103515245u + 12345u;
  return (double) ((seed >> 16) & 0x7fff) / 32767.0 - 0.5;
}

static void
make_pattern (double *ref)      /* the sensor's fixed per-sensel offsets */
{
  for (int i = 0; i < N; i++)
    ref[i] = 128.0 + 60.0 * rnd ();
}

static void
to_frame (const double *v, uint8_t *out)
{
  for (int i = 0; i < N; i++)
    out[i] = (uint8_t) (v[i] < 0 ? 0 : v[i] > 255 ? 255 : v[i]);
}

static int failures = 0;

static void
check (const char *what, int ok, double got)
{
  printf ("  %-52s %-4s (r = %.4f)\n", what, ok ? "ok" : "FAIL", got);
  if (!ok)
    failures++;
}

int
main (void)
{
  double pat[N], v[N];
  uint8_t baseline[N], blank[N], press[N], gain6_blank[N];

  make_pattern (pat);
  to_frame (pat, baseline);

  /* a no-finger frame: the same fixed pattern, plus read noise */
  for (int i = 0; i < N; i++)
    v[i] = pat[i] + 2.0 * rnd ();
  to_frame (v, blank);

  /* a no-finger frame at higher gain: the same pattern, amplified about the
   * midpoint. Correlation is scale-invariant, which is why one reference
   * catches blanks at either gain. */
  for (int i = 0; i < N; i++)
    v[i] = 128.0 + 2.4 * (pat[i] - 128.0) + 2.0 * rnd ();
  to_frame (v, gain6_blank);

  /* a real press: ridges dominate the fixed pattern */
  for (int i = 0; i < N; i++)
    v[i] = pat[i] + 55.0 * sin ((double) (i % W) * 0.9 + (double) (i / W) * 0.35);
  to_frame (v, press);

  printf ("blank-frame gate, synthetic frames (threshold %.2f)\n",
          EGIS0576_BLANK_THRESHOLD);

  double r_blank = egis_blank_agreement (blank, baseline, N);
  double r_g6    = egis_blank_agreement (gain6_blank, baseline, N);
  double r_press = egis_blank_agreement (press, baseline, N);

  check ("no-finger frame is rejected", egis_blank_is_blank (blank, baseline, N), r_blank);
  check ("no-finger frame at higher gain is rejected",
         egis_blank_is_blank (gain6_blank, baseline, N), r_g6);
  check ("a real press is accepted", !egis_blank_is_blank (press, baseline, N), r_press);
  check ("the gate leaves usable margin either side",
         r_blank - r_press > 0.30, r_blank - r_press);

  /* with no reference yet, the gate must never reject: enrolment cannot be
   * blocked because we have not seen an empty sensor */
  check ("fails open when no reference has been collected",
         !egis_blank_is_blank (blank, NULL, N), 0.0);

  printf ("%s\n", failures ? "FAILED" : "all checks passed");
  return failures ? 1 : 0;
}
