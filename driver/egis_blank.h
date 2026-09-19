/*
 * Blank-frame rejection for the EgisTec EH576.
 *
 * A frame captured with no finger on the sensor is not empty: it is the
 * sensor's fixed per-sensel pattern, and the coherence mask finds "ridges" in
 * that pattern. Such a frame therefore passes a coverage gate happily. It is
 * also indistinguishable from a real press by frame variance once the gain is
 * high enough for the fixed pattern to carry more variance than a fingertip.
 *
 * The cheap test is that a no-finger frame correlates near 1 with a no-finger
 * reference, because it IS the reference plus read noise, while a frame with a
 * finger on it does not. Measured on a Yoga 7 16IRL8 against a gain-0
 * reference:
 *
 *   real presses, gain 0 (n=40)            0.258 .. 0.537
 *   real presses, gain 6 (n=64)            0.348 .. 0.533
 *   no-finger frames, gain 0 (leave-one-out) 0.970 .. 0.972
 *   no-finger frames, gain 6                 0.981 .. 0.985
 *
 * Nothing lands between 0.537 and 0.970, and the threshold below sits in that
 * gap. Note the third and fourth rows: Pearson correlation is scale-invariant
 * and this sensor's gain-0 and gain-6 fixed patterns correlate 0.9915 with
 * each other, so a reference collected at one gain detects blanks at the
 * other. The driver captures at gain 0 only (see egis0576.c), so this costs
 * nothing today and keeps working if a second gain ever returns.
 *
 * Why this matters most at enrolment: a blank probe simply fails to match and
 * the user presses again, but a blank enrolment frame is accepted into the
 * template, silently spends one of the enrolment stages and leaves a hole in
 * the covered area that the user never learns about. One was found in a
 * labelled capture set that had already been screened by hand.
 *
 * tools/blank_gate_test.c checks the property on synthetic frames;
 * tools/blank_gate_check.py measures the two populations on real captures.
 *
 * This library is free software; you can redistribute it and/or modify it
 * under the terms of the GNU Lesser General Public License as published by the
 * Free Software Foundation; either version 2.1 of the License, or (at your
 * option) any later version.
 */

#ifndef __EGIS_BLANK_H
#define __EGIS_BLANK_H 1

#include <stddef.h>
#include <stdint.h>
#include <math.h>

/* Correlation at or above which a frame is taken to show an empty sensor.
 * 0.26 clear of the worst real press measured, 0.17 clear of the nearest
 * no-finger frame. */
#define EGIS0576_BLANK_THRESHOLD 0.80

/* Pearson correlation between a frame and a no-finger reference.
 *
 * Returns -1.0 when there is no reference, or when either frame is perfectly
 * flat and the correlation is undefined. Callers treat that as "cannot tell",
 * never as "blank". */
static inline double
egis_blank_agreement (const uint8_t *frame, const uint8_t *baseline, size_t n)
{
  double fs = 0.0, bs = 0.0;

  if (!frame || !baseline || n == 0)
    return -1.0;

  for (size_t i = 0; i < n; i++)
    {
      fs += frame[i];
      bs += baseline[i];
    }

  double fm = fs / (double) n, bm = bs / (double) n;
  double num = 0.0, fv = 0.0, bv = 0.0;

  for (size_t i = 0; i < n; i++)
    {
      double df = (double) frame[i] - fm;
      double db = (double) baseline[i] - bm;
      num += df * db;
      fv += df * df;
      bv += db * db;
    }

  if (fv <= 0.0 || bv <= 0.0)
    return -1.0;

  return num / sqrt (fv * bv);
}

/* True when the frame shows an empty sensor. Fails open: with no reference
 * collected yet, nothing is ever rejected, so enrolment can never be blocked
 * for want of a baseline. */
static inline int
egis_blank_is_blank (const uint8_t *frame, const uint8_t *baseline, size_t n)
{
  double r = egis_blank_agreement (frame, baseline, n);

  return r >= EGIS0576_BLANK_THRESHOLD;
}

#endif
