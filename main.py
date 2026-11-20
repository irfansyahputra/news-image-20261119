#!/usr/bin/env python3
"""THE WORLD — one-image newspaper front page for Thursday, 19 November 2026.

Entry for the make.fun bounty "news-image-20261119" (program/v1 harness).
Pure Python standard library: the whole page — masthead, headlines, body
text and every illustration — is drawn by this program into a 1024x1024
framebuffer and written out as a PNG. No network, no randomness, no clock:
two runs produce byte-identical output.

Usage:
    python3 main.py [output-path]
The image is written to /output/entry.png when no path is given (the
output directory is created when missing).
"""

import os
import struct
import sys
import zlib
from math import cos, pi, sin, sqrt

W = H = 1024

# ---------------------------------------------------------------- palette
PAPER = (250, 244, 227)      # warm cream newsprint
INK = (26, 30, 44)           # body text, near-black navy
NAVY = (13, 30, 64)          # masthead band / headline navy
NAVY_TX = (18, 38, 76)       # headline text navy
GOLD = (232, 184, 75)        # masthead gold
RED = (178, 32, 44)          # accent red
GREY = (84, 88, 102)         # deck / secondary text
RULE = (120, 110, 88)        # hairline rules on paper
BLUE_K = (30, 80, 160)       # Berlin kicker
ORNG_K = (196, 84, 32)       # Hormuz kicker
TEAL_K = (24, 110, 104)      # Kim kicker

fb = bytearray(bytes(PAPER) * (W * H))


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def fill_rect(x0, y0, x1, y1, c):
    """Fill the rectangle [x0,x1) x [y0,y1) with colour c."""
    x0 = _clamp(int(round(x0)), 0, W)
    x1 = _clamp(int(round(x1)), 0, W)
    y0 = _clamp(int(round(y0)), 0, H)
    y1 = _clamp(int(round(y1)), 0, H)
    if x1 <= x0 or y1 <= y0:
        return
    row = bytes(c) * (x1 - x0)
    off = (y0 * W + x0) * 3
    for _ in range(y0, y1):
        fb[off:off + len(row)] = row
        off += W * 3


def fill_disc(cx, cy, r, c):
    """Filled circle of radius r centred at (cx, cy)."""
    if r <= 0:
        return
    y_lo = max(0, int(cy - r - 1))
    y_hi = min(H - 1, int(cy + r + 1))
    pix = bytes(c)
    for y in range(y_lo, y_hi + 1):
        dy = (y + 0.5) - cy
        rem = r * r - dy * dy
        if rem < 0:
            continue
        half = sqrt(rem)
        x0 = max(0, int(cx - half))
        x1 = min(W - 1, int(cx + half))
        off = (y * W + x0) * 3
        fb[off:off + (x1 - x0 + 1) * 3] = pix * (x1 - x0 + 1)


def fill_ellipse(cx, cy, rx, ry, c, top_only=False, bottom_only=False):
    """Filled ellipse; optionally only its top or bottom half."""
    y_lo = max(0, int(cy - ry - 1))
    y_hi = min(H - 1, int(cy + ry + 1))
    pix = bytes(c)
    for y in range(y_lo, y_hi + 1):
        dy = (y + 0.5) - cy
        if top_only and dy > 0:
            continue
        if bottom_only and dy < 0:
            continue
        t = 1.0 - (dy * dy) / (ry * ry)
        if t < 0:
            continue
        half = rx * sqrt(t)
        x0 = max(0, int(cx - half))
        x1 = min(W - 1, int(cx + half))
        off = (y * W + x0) * 3
        fb[off:off + (x1 - x0 + 1) * 3] = pix * (x1 - x0 + 1)


def fill_poly(points, c):
    """Filled polygon from a list of (x, y) points (scanline, even-odd)."""
    if len(points) < 3:
        return
    ys = [p[1] for p in points]
    y_lo = max(0, int(min(ys)))
    y_hi = min(H - 1, int(max(ys)))
    pix = bytes(c)
    n = len(points)
    for y in range(y_lo, y_hi + 1):
        yc = y + 0.5
        xs = []
        for i in range(n):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % n]
            if (y1 <= yc < y2) or (y2 <= yc < y1):
                xs.append(x1 + (yc - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            x0 = max(0, int(xs[i]))
            x1 = min(W - 1, int(xs[i + 1]))
            if x1 >= x0:
                off = (y * W + x0) * 3
                fb[off:off + (x1 - x0 + 1) * 3] = pix * (x1 - x0 + 1)


def thick_line(x0, y0, x1, y1, w, c):
    """Line with round caps, drawn by stamping discs along the segment."""
    r = w / 2.0
    dist = sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
    steps = max(1, int(dist / max(0.6, r * 0.4)))
    for i in range(steps + 1):
        t = i / steps
        fill_disc(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r, c)


def polyline(points, w, c, close=False):
    pts = list(points)
    if close and len(pts) > 2:
        pts.append(pts[0])
    for i in range(len(pts) - 1):
        thick_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], w, c)


def star_points(cx, cy, r_outer, r_inner=None, rot=-pi / 2):
    if r_inner is None:
        r_inner = r_outer * 0.45
    pts = []
    for i in range(10):
        r = r_outer if i % 2 == 0 else r_inner
        a = rot + i * pi / 5
        pts.append((cx + r * cos(a), cy + r * sin(a)))
    return pts


def fill_star(cx, cy, r, c):
    fill_poly(star_points(cx, cy, r), c)


# ------------------------------------------------------------------- font
# A hand-drawn stroke font. Each glyph lives on a grid where x runs over
# the glyph width and y runs 0 (cap top) .. 7 (baseline); lowercase
# ascenders reach y=0, x-height starts at y=2.5, descenders reach y=9.3.
# Entry: char -> (advance_units, [stroke, ...], [(dot_x, dot_y, dot_r), ...])
# A stroke is a list of (x, y) points drawn as one polyline.
FONT = {
    'A': (5.3, [[(0, 7), (2, 0), (4, 7)], [(1.05, 4.5), (2.95, 4.5)]], []),
    'B': (4.9, [[(0, 0), (0, 7)],
                [(0, 0), (2.3, 0), (3.3, 0.9), (3.3, 2.3), (2.3, 3.3), (0, 3.3)],
                [(0, 3.3), (2.6, 3.3), (3.6, 4.2), (3.6, 5.9), (2.6, 7), (0, 7)]], []),
    'C': (5.0, [[(3.7, 1.3), (2.7, 0.2), (1.2, 0), (0.3, 1.1), (0, 3.5),
                 (0.3, 5.9), (1.2, 7), (2.7, 7), (3.7, 5.7)]], []),
    'D': (5.2, [[(0, 0), (0, 7)],
                [(0, 0), (2.1, 0), (3.5, 1.3), (3.9, 3.5), (3.5, 5.7), (2.1, 7), (0, 7)]], []),
    'E': (4.8, [[(3.5, 0), (0, 0), (0, 7), (3.5, 7)], [(0, 3.5), (2.8, 3.5)]], []),
    'F': (4.8, [[(3.5, 0), (0, 0), (0, 7)], [(0, 3.5), (2.6, 3.5)]], []),
    'G': (5.1, [[(3.7, 1.3), (2.7, 0.2), (1.2, 0), (0.3, 1.1), (0, 3.5),
                 (0.3, 5.9), (1.2, 7), (2.8, 7), (3.8, 5.9), (3.8, 3.9), (2.3, 3.9)]], []),
    'H': (5.3, [[(0, 0), (0, 7)], [(4, 0), (4, 7)], [(0, 3.5), (4, 3.5)]], []),
    'I': (2.8, [[(1.4, 0), (1.4, 7)]], []),
    'J': (4.9, [[(3.6, 0), (3.6, 5.5), (2.7, 6.7), (1.3, 7), (0.3, 6.1)]], []),
    'K': (5.3, [[(0, 0), (0, 7)], [(3.9, 0), (0.3, 3.5)], [(0.8, 3.1), (4, 7)]], []),
    'L': (4.8, [[(0, 0), (0, 7), (3.5, 7)]], []),
    'M': (5.9, [[(0, 7), (0, 0), (2.3, 3.4), (4.6, 0), (4.6, 7)]], []),
    'N': (5.3, [[(0, 7), (0, 0), (4, 7), (4, 0)]], []),
    'O': (5.3, [[(1.3, 0), (2.7, 0), (3.8, 1.2), (4, 3.5), (3.8, 5.8),
                 (2.7, 7), (1.3, 7), (0.2, 5.8), (0, 3.5), (0.2, 1.2), (1.3, 0)]], []),
    'P': (4.8, [[(0, 7), (0, 0), (2.4, 0), (3.4, 1), (3.4, 2.5), (2.4, 3.5), (0, 3.5)]], []),
    'Q': (5.5, [[(1.3, 0), (2.7, 0), (3.8, 1.2), (4, 3.5), (3.8, 5.8),
                 (2.7, 7), (1.3, 7), (0.2, 5.8), (0, 3.5), (0.2, 1.2), (1.3, 0)],
                [(2.5, 5.0), (4.3, 7.3)]], []),
    'R': (5.2, [[(0, 7), (0, 0), (2.4, 0), (3.4, 1), (3.4, 2.5), (2.4, 3.5), (0, 3.5)],
                [(1.7, 3.5), (3.9, 7)]], []),
    'S': (5.0, [[(3.6, 1.2), (2.7, 0.1), (1.2, 0), (0.2, 1), (0.3, 2.3), (1.3, 3.2),
                 (2.7, 3.9), (3.6, 4.8), (3.5, 6.1), (2.5, 7), (1, 7), (0.1, 6)]], []),
    'T': (5.3, [[(0, 0), (4, 0)], [(2, 0), (2, 7)]], []),
    'U': (5.3, [[(0, 0), (0, 5.3), (0.6, 6.5), (1.9, 7), (3.4, 6.5), (4, 5.3), (4, 0)]], []),
    'V': (5.3, [[(0, 0), (2, 7), (4, 0)]], []),
    'W': (5.9, [[(0, 0), (0.9, 7), (2.3, 3.2), (3.7, 7), (4.6, 0)]], []),
    'X': (5.3, [[(0, 0), (4, 7)], [(4, 0), (0, 7)]], []),
    'Y': (5.3, [[(0, 0), (2, 3.3)], [(4, 0), (2, 3.3)], [(2, 3.3), (2, 7)]], []),
    'Z': (5.3, [[(0, 0), (4, 0), (0, 7), (4, 7)]], []),
    'a': (4.8, [[(3.6, 2.5), (3.6, 7)],
                [(3.6, 3.9), (2.6, 2.6), (1.2, 2.5), (0.3, 3.7), (0.2, 5.5),
                 (0.8, 6.8), (2.2, 7), (3.6, 6.3)]], []),
    'b': (4.8, [[(0.2, 0), (0.2, 7)],
                [(0.2, 3.9), (1.2, 2.7), (2.6, 2.5), (3.5, 3.6), (3.6, 5.3),
                 (2.9, 6.7), (1.6, 7), (0.2, 6.3)]], []),
    'c': (4.6, [[(3.5, 3.4), (2.7, 2.6), (1.4, 2.5), (0.4, 3.6), (0.2, 5.2),
                 (0.8, 6.6), (2, 7), (3.3, 6.4), (3.6, 5.6)]], []),
    'd': (4.8, [[(3.6, 0), (3.6, 7)],
                [(3.6, 3.9), (2.6, 2.6), (1.2, 2.5), (0.3, 3.7), (0.2, 5.5),
                 (0.8, 6.8), (2.2, 7), (3.6, 6.3)]], []),
    'e': (4.7, [[(0.3, 4.4), (3.5, 4.4), (3.4, 3.4), (2.6, 2.6), (1.3, 2.5),
                 (0.4, 3.5), (0.2, 5.4), (0.8, 6.7), (2.1, 7), (3.4, 6.3)]], []),
    'f': (3.6, [[(2.7, 0.7), (1.9, 0), (1.1, 0.7), (1, 2.5), (1, 7)],
                [(0.1, 2.7), (2.4, 2.7)]], []),
    'g': (4.8, [[(3.6, 2.5), (3.6, 8.3), (2.9, 9.2), (1.6, 9.4), (0.5, 8.8)],
                [(3.6, 3.9), (2.6, 2.6), (1.2, 2.5), (0.3, 3.7), (0.2, 5.5),
                 (0.8, 6.8), (2.2, 7), (3.6, 6.3)]], []),
    'h': (5.0, [[(0.2, 0), (0.2, 7)],
                [(0.2, 4.3), (1, 3), (2.4, 2.5), (3.5, 3.2), (3.7, 4.6), (3.7, 7)]], []),
    'i': (2.2, [[(0.5, 2.5), (0.5, 7)]], [(0.5, 0.8, 0.42)]),
    'j': (2.8, [[(1.1, 2.5), (1.1, 8.2), (0.5, 9.2), (0, 9.3)]], [(1.1, 0.8, 0.42)]),
    'k': (4.7, [[(0.2, 0), (0.2, 7)], [(3.5, 2.5), (0.4, 5)], [(1.1, 4.3), (3.7, 7)]], []),
    'l': (2.2, [[(0.5, 0), (0.5, 7)]], []),
    'm': (6.8, [[(0.2, 2.5), (0.2, 7)],
                [(0.2, 4.2), (0.9, 2.9), (2, 2.5), (2.8, 3.1), (2.9, 4.6), (2.9, 7)],
                [(2.9, 4.2), (3.8, 2.9), (4.9, 2.5), (5.7, 3.1), (5.8, 4.6), (5.8, 7)]], []),
    'n': (5.0, [[(0.2, 2.5), (0.2, 7)],
                [(0.2, 4.3), (1, 3), (2.4, 2.5), (3.5, 3.2), (3.7, 4.6), (3.7, 7)]], []),
    'o': (4.8, [[(1.1, 2.5), (2.5, 2.5), (3.4, 3.6), (3.6, 4.8), (3.3, 6.3),
                 (2.4, 7), (1.1, 7), (0.3, 6.2), (0.1, 4.7), (0.3, 3.5), (1.1, 2.5)]], []),
    'p': (4.8, [[(0.2, 2.5), (0.2, 9.3)],
                [(0.2, 3.9), (1.2, 2.7), (2.6, 2.5), (3.5, 3.6), (3.6, 5.3),
                 (2.9, 6.7), (1.6, 7), (0.2, 6.3)]], []),
    'q': (4.8, [[(3.6, 2.5), (3.6, 9.2)],
                [(3.6, 3.9), (2.6, 2.6), (1.2, 2.5), (0.3, 3.7), (0.2, 5.5),
                 (0.8, 6.8), (2.2, 7), (3.6, 6.3)]], []),
    'r': (4.0, [[(0.2, 2.5), (0.2, 7)], [(0.2, 4.1), (1, 2.9), (2.2, 2.5), (3, 2.9)]], []),
    's': (4.5, [[(3.3, 3.3), (2.5, 2.6), (1.2, 2.5), (0.3, 3.2), (0.5, 4.4), (1.5, 5),
                 (2.8, 5.6), (3.3, 6.3), (2.7, 7), (1.2, 7), (0.2, 6.4)]], []),
    't': (3.9, [[(1.3, 0.8), (1.3, 6.2), (1.9, 7), (2.8, 6.9)], [(0.2, 2.7), (2.7, 2.7)]], []),
    'u': (5.0, [[(0.2, 2.5), (0.2, 5.6), (0.8, 6.7), (2.1, 7), (3.6, 6.1)],
                [(3.7, 2.5), (3.7, 7)]], []),
    'v': (5.0, [[(0, 2.5), (1.9, 7), (3.8, 2.5)]], []),
    'w': (5.8, [[(0, 2.5), (0.8, 7), (2.2, 4.1), (3.6, 7), (4.6, 2.5)]], []),
    'x': (4.8, [[(0.1, 2.5), (3.5, 7)], [(3.5, 2.5), (0.1, 7)]], []),
    'y': (5.0, [[(0, 2.5), (1.9, 6.2)], [(3.8, 2.5), (1.9, 6.2), (1.2, 8.6), (0.4, 9.3)]], []),
    'z': (4.6, [[(0.2, 2.5), (3.4, 2.5), (0.2, 7), (3.5, 7)]], []),
    '0': (5.0, [[(1.2, 0), (2.6, 0), (3.6, 1.2), (3.8, 3.5), (3.6, 5.8),
                 (2.6, 7), (1.2, 7), (0.2, 5.8), (0, 3.5), (0.2, 1.2), (1.2, 0)]], []),
    '1': (5.0, [[(1.1, 1.3), (2.5, 0), (2.5, 7)], [(0.8, 7), (4, 7)]], []),
    '2': (5.0, [[(0.3, 1.1), (1.1, 0.1), (2.5, 0), (3.5, 0.9), (3.4, 2.2), (0.2, 7), (3.9, 7)]], []),
    '3': (5.0, [[(0.3, 1), (1.2, 0.1), (2.5, 0), (3.4, 1), (3.2, 2.4), (2.1, 3.3)],
                [(2.1, 3.3), (3.3, 4.2), (3.4, 5.8), (2.5, 6.9), (1.1, 7), (0.2, 6)]], []),
    '4': (5.2, [[(2.9, 7), (2.9, 0)], [(2.9, 0), (0, 4.9), (4.1, 4.9)]], []),
    '5': (5.0, [[(3.7, 0), (0.4, 0), (0.3, 3.1), (2.1, 2.8), (3.4, 3.7), (3.5, 5.6),
                 (2.6, 6.9), (1.1, 7), (0.2, 6)]], []),
    '6': (5.0, [[(3.4, 1.3), (2.3, 0.2), (1.1, 0.5), (0.3, 2.1), (0.1, 4.8), (0.6, 6.4),
                 (1.7, 7), (3, 6.6), (3.6, 5.4), (3.2, 3.9), (2, 3.2), (0.8, 3.6), (0.1, 4.8)]], []),
    '7': (5.0, [[(0.2, 0), (3.9, 0), (1.8, 7)]], []),
    '8': (5.0, [[(1.9, 3.4), (1, 2.8), (0.7, 1.5), (1.3, 0.3), (2.5, 0.1), (3.3, 0.9),
                 (3.1, 2.6), (1.9, 3.4)],
                [(1.9, 3.4), (0.9, 4.3), (0.7, 5.8), (1.4, 6.9), (2.6, 7), (3.5, 6.1),
                 (3.3, 4.5), (1.9, 3.4)]], []),
    '9': (5.0, [[(0.4, 5.7), (1.7, 6.8), (2.9, 6.5), (3.7, 4.9), (3.9, 2.1), (3.3, 0.5),
                 (2, 0), (0.7, 0.5), (0.2, 1.9), (0.6, 3.2), (1.9, 3.8), (3.1, 3.3), (3.9, 2.1)]], []),
    ' ': (2.6, [], []),
    '.': (2.2, [], [(0.6, 6.9, 0.45)]),
    ',': (2.2, [[(0.9, 7), (0.4, 8.2)]], [(0.7, 6.7, 0.42)]),
    ':': (2.2, [], [(0.6, 2.9, 0.42), (0.6, 6.9, 0.42)]),
    ';': (2.2, [[(0.9, 7), (0.4, 8.2)]], [(0.6, 2.9, 0.42), (0.7, 6.7, 0.42)]),
    "'": (1.8, [[(0.7, 0), (0.4, 1.6)]], []),
    '"': (2.6, [[(0.5, 0), (0.2, 1.6)], [(1.7, 0), (1.4, 1.6)]], []),
    '-': (3.4, [[(0.2, 3.8), (2.4, 3.8)]], []),
    '–': (4.2, [[(0.2, 3.8), (3.2, 3.8)]], []),
    '—': (5.4, [[(0.1, 3.8), (4.4, 3.8)]], []),
    '·': (2.2, [], [(0.6, 3.9, 0.4)]),
    '•': (2.6, [], [(0.8, 3.9, 0.62)]),
    '/': (3.4, [[(0.4, 7.4), (2.6, -0.4)]], []),
    '(': (3.0, [[(2.4, 0), (1.2, 1.2), (0.7, 3.5), (1.2, 5.8), (2.4, 7)]], []),
    ')': (3.0, [[(0.6, 0), (1.8, 1.2), (2.3, 3.5), (1.8, 5.8), (0.6, 7)]], []),
    '€': (5.2, [[(3.8, 1.2), (2.8, 0.2), (1.3, 0), (0.4, 1.1), (0.1, 3.5),
                 (0.4, 5.9), (1.3, 7), (2.8, 7), (3.8, 5.8)],
                [(0.5, 2.9), (3.1, 2.9)], [(0.5, 4.3), (3.1, 4.3)]], []),
    '$': (5.0, [[(3.5, 1.2), (2.6, 0.1), (1.2, 0), (0.2, 1), (0.4, 2.3), (1.3, 3.2),
                 (2.6, 3.9), (3.5, 4.8), (3.4, 6.1), (2.4, 7), (1, 7), (0.1, 6)],
                [(1.9, -0.3), (1.9, 7.3)]], []),
    '%': (5.6, [[(4.6, 0), (0.6, 7)],
                [(0.9, 0.4), (1.6, 0.7), (1.7, 1.6), (1.2, 2.3), (0.5, 2), (0.3, 1.1), (0.9, 0.4)],
                [(3.9, 4.7), (4.6, 5), (4.7, 5.9), (4.2, 6.6), (3.5, 6.3), (3.3, 5.4), (3.9, 4.7)]], []),
    '+': (4.3, [[(1.7, 1.6), (1.7, 5.6)], [(0.1, 3.6), (3.3, 3.6)]], []),
    '!': (2.2, [[(0.6, 0), (0.6, 4.9)]], [(0.6, 6.9, 0.42)]),
    '?': (4.6, [[(0.3, 1.1), (1.1, 0.1), (2.5, 0), (3.3, 1), (3, 2.3), (1.9, 3.4), (1.9, 4.9)]],
          [(1.9, 6.9, 0.42)]),
}
FONT_FALLBACK = (4.6, [], [])
ALIASES = {'’': "'", '‘': "'", '“': '"', '”': '"', '‐': '-'}


def glyph(ch):
    return FONT.get(ALIASES.get(ch, ch), FONT_FALLBACK)


def text_width(s, size, tracking=0.0):
    scale = size / 7.0
    w = sum(glyph(ch)[0] for ch in s) * scale
    if len(s) > 1:
        w += tracking * (len(s) - 1)
    return w


def draw_text(x, y, s, size, color, bold=False, align='left', tracking=0.0):
    """Draw text with the glyph-grid top at y; returns the drawn width."""
    if bold:
        tracking += size * 0.045  # bold strokes eat the side bearings; add air
    w = text_width(s, size, tracking)
    if align == 'center':
        x -= w / 2.0
    elif align == 'right':
        x -= w
    scale = size / 7.0
    sw = max(1.1, size * (0.148 if bold else 0.118))
    cx = x
    for ch in s:
        adv, strokes, dots = glyph(ch)
        for stroke in strokes:
            pts = [(cx + gx * scale, y + gy * scale) for gx, gy in stroke]
            polyline(pts, sw, color)
        for dx, dy, dr in dots:
            fill_disc(cx + dx * scale, y + dy * scale, max(0.7, dr * scale), color)
        cx += adv * scale + tracking
    return w


def wrap_words(s, size, max_width, tracking=0.0):
    """Greedy word wrap; returns a list of lines fitting max_width."""
    lines = []
    cur = ''
    for word in s.split(' '):
        trial = word if not cur else cur + ' ' + word
        if text_width(trial, size, tracking) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_paragraph(x, y, s, size, color, line_height, widths, bold=False):
    """Wrap s over per-line widths (list of (dx, width); the last repeats).

    Returns the y just past the last drawn line.
    """
    words = s.split(' ')
    lines = []
    wi = 0
    cur = ''
    while wi < len(words):
        dx, mw = widths[min(len(lines), len(widths) - 1)]
        trial = words[wi] if not cur else cur + ' ' + words[wi]
        if text_width(trial, size) <= mw or not cur:
            cur = trial
            wi += 1
        else:
            lines.append(cur)
            cur = ''
    if cur:
        lines.append(cur)
    for i, line in enumerate(lines):
        dx, _ = widths[min(i, len(widths) - 1)]
        draw_text(x + dx, y + i * line_height, line, size, color, bold)
    return y + len(lines) * line_height


# ------------------------------------------------------------------ flags
def border(x, y, w, h, c, t=2):
    fill_rect(x, y, x + w, y + t, c)
    fill_rect(x, y + h - t, x + w, y + h, c)
    fill_rect(x, y, x + t, y + h, c)
    fill_rect(x + w - t, y, x + w, y + h, c)


def flag_us(x, y, w, h):
    fill_rect(x, y, x + w, y + h, (246, 246, 244))
    sh = h / 13.0
    for i in range(0, 13, 2):
        fill_rect(x, y + i * sh, x + w, y + (i + 1) * sh, (178, 34, 52))
    cw, chh = w * 0.42, sh * 7
    fill_rect(x, y, x + cw, y + chh, (60, 59, 110))
    for r in range(4):
        for cix in range(5):
            dx = x + 3 + cix * (cw - 5) / 4.0
            dy = y + 3 + r * (chh - 5) / 3.0
            fill_rect(dx - 1, dy - 1, dx + 1, dy + 1, (255, 255, 255))


def flag_cn(x, y, w, h):
    fill_rect(x, y, x + w, y + h, (222, 41, 41))
    fill_star(x + w * 0.24, y + h * 0.30, h * 0.17, (255, 222, 0))
    for dx, dy in ((0.38, 0.13), (0.44, 0.28), (0.44, 0.45), (0.38, 0.62)):
        fill_star(x + w * dx, y + h * dy, h * 0.055, (255, 222, 0))


def flag_ru(x, y, w, h):
    fill_rect(x, y, x + w, y + h / 3.0, (245, 245, 245))
    fill_rect(x, y + h / 3.0, x + w, y + 2 * h / 3.0, (30, 90, 170))
    fill_rect(x, y + 2 * h / 3.0, x + w, y + h, (213, 43, 30))


def flag_de(x, y, w, h):
    fill_rect(x, y, x + w, y + h / 3.0, (25, 25, 28))
    fill_rect(x, y + h / 3.0, x + w, y + 2 * h / 3.0, (221, 0, 0))
    fill_rect(x, y + 2 * h / 3.0, x + w, y + h, (240, 190, 30))


def flag_fr(x, y, w, h):
    fill_rect(x, y, x + w / 3.0, y + h, (0, 85, 164))
    fill_rect(x + w / 3.0, y, x + 2 * w / 3.0, y + h, (246, 246, 244))
    fill_rect(x + 2 * w / 3.0, y, x + w, y + h, (239, 65, 70))


def flag_ua(x, y, w, h):
    fill_rect(x, y, x + w, y + h / 2.0, (0, 91, 187))
    fill_rect(x, y + h / 2.0, x + w, y + h, (255, 213, 0))


def flag_nk(x, y, w, h):
    fill_rect(x, y, x + w, y + h, (2, 68, 146))
    fill_rect(x, y + h * 0.16, x + w, y + h * 0.84, (246, 246, 244))
    fill_rect(x, y + h * 0.25, x + w, y + h * 0.75, (237, 28, 39))
    fill_disc(x + w * 0.30, y + h * 0.5, h * 0.20, (246, 246, 244))
    fill_star(x + w * 0.30, y + h * 0.5, h * 0.145, (237, 28, 39))


# ------------------------------------------------------------ illustrations
def lead_illustration(x, y, w, h):
    """Three leaders at a round table, flags behind, Shenzhen skyline at dawn."""
    fill_rect(x - 3, y - 3, x + w + 3, y + h + 3, NAVY)
    # dawn sky in flat bands
    bands = [(0.00, (38, 54, 96)), (0.30, (92, 84, 124)), (0.48, (196, 110, 70)),
             (0.60, (233, 152, 82)), (0.70, (24, 34, 62))]
    for i, (f0, c) in enumerate(bands):
        f1 = bands[i + 1][0] if i + 1 < len(bands) else 1.0
        fill_rect(x, y + f0 * h, x + w, y + f1 * h, c)
    # sun and halo
    fill_disc(x + 352, y + 104, 36, (238, 178, 96))
    fill_disc(x + 352, y + 104, 24, (248, 202, 96))
    # skyline silhouettes (baseline at 0.70*h)
    base = y + 0.70 * h
    dark = (18, 28, 54)
    for dx, bw, bh in [(0, 54, 62), (50, 40, 86), (86, 60, 50), (142, 36, 94),
                       (174, 58, 68), (228, 42, 82), (266, 64, 56), (326, 38, 90),
                       (360, 56, 64), (412, 58, 78)]:
        fill_rect(x + dx, base - bh, x + dx + bw, base, dark)
        for wy in range(int(base - bh) + 8, int(base) - 6, 11):
            for wx in range(x + dx + 6, x + dx + bw - 6, 9):
                if (wx * 7 + wy * 13) % 4 == 0:
                    fill_rect(wx, wy, wx + 3, wy + 4, (240, 200, 110))
    # terrace floor
    fill_rect(x, base, x + w, y + h, (22, 32, 58))
    fill_rect(x, base, x + w, base + 4, (60, 70, 100))
    # flags on poles: United States, China, Russia
    for dx, draw in ((58, flag_us), (235, flag_cn), (412, flag_ru)):
        fill_rect(x + dx - 1.5, y + 16, x + dx + 1.5, y + 128, (150, 154, 162))
        fill_disc(x + dx, y + 14, 3.2, GOLD)
        draw(x + dx + 3, y + 18, 62, 42)
    # the three leaders, seated
    leaders = [
        (118, (30, 40, 74), (224, 172, 128), (228, 192, 110), RED),        # Trump
        (235, (22, 24, 32), (232, 186, 152), (20, 20, 24), (140, 30, 40)),  # Xi
        (352, (32, 36, 56), (236, 196, 164), None, (50, 80, 160)),          # Putin
    ]
    hcy = y + 148
    for cxr, suit, skin, hair, tie in leaders:
        cx = x + cxr
        fill_poly([(cx - 46, y + h), (cx - 38, y + 172), (cx + 38, y + 172),
                   (cx + 46, y + h)], suit)
        fill_poly([(cx - 9, y + 174), (cx + 9, y + 174), (cx, y + 192)], (245, 245, 240))
        fill_poly([(cx - 3.2, y + 176), (cx + 3.2, y + 176), (cx + 2, y + 200),
                   (cx, y + 205), (cx - 2, y + 200)], tie)
        fill_disc(cx, hcy, 20, skin)
        if hair is not None:
            fill_ellipse(cx, hcy - 6, 20, 14, hair, top_only=True)
    # round table with a gold rim and name plates
    tcx, tcy = x + 235, y + 224
    fill_rect(tcx - 10, tcy + 2, tcx + 10, y + h, (60, 20, 26))
    fill_ellipse(tcx, tcy, 126, 24, GOLD)
    fill_ellipse(tcx, tcy - 2, 122, 21, (122, 30, 38))
    for cxr in (118, 235, 352):
        fill_rect(x + cxr - 15, y + 212, x + cxr + 15, y + 221, (245, 240, 220))
        fill_rect(x + cxr - 9, y + 215.5, x + cxr + 9, y + 217.5, NAVY)


def berlin_banner(x, y, w, h):
    """Chancellery dome and TV tower over a Berlin skyline, with allied flags."""
    fill_rect(x, y, x + w, y + h, (168, 196, 224))
    fill_ellipse(x + 70, y + 16, 30, 7, (240, 246, 252))
    fill_ellipse(x + 330, y + 12, 24, 6, (240, 246, 252))
    base = y + h - 6
    for dx, bw, bh in [(0, 60, 30), (56, 44, 42), (330, 52, 36), (378, 40, 26),
                       (250, 46, 30), (96, 40, 24)]:
        fill_rect(x + dx, base - bh, x + dx + bw, base, (148, 154, 166))
    # chancellery block with a teal dome
    fill_rect(x + 150, y + 44, x + 262, base, (172, 176, 186))
    for i in range(6):
        fill_rect(x + 159 + i * 17, y + 52, x + 162 + i * 17, base - 6, (230, 234, 240))
    fill_ellipse(x + 206, y + 44, 40, 32, (46, 110, 108), top_only=True)
    fill_rect(x + 204, y + 8, x + 208, y + 16, (90, 96, 110))
    fill_disc(x + 206, y + 7, 3, GOLD)
    # TV tower
    fill_rect(x + 392, y + 26, x + 397, base, (120, 126, 138))
    fill_disc(x + 394, y + 30, 10, (178, 184, 194))
    fill_disc(x + 394, y + 6, 2.5, (200, 60, 60))
    # allied flags: Germany, France, Ukraine
    for dx, draw in ((24, flag_de), (76, flag_fr), (128, flag_ua)):
        fill_rect(x + dx - 1, y + 42, x + dx + 1, base, (110, 114, 124))
        draw(x + dx + 2, y + 44, 40, 26)
    fill_rect(x, base, x + w, y + h, (96, 116, 96))
    border(x, y, w, h, NAVY, 2)


def hormuz_banner(x, y, w, h):
    """A burning supertanker in a narrow strait, with a $92 price tag."""
    fill_rect(x, y, x + w, y + h, (36, 92, 140))
    tan = (198, 164, 112)
    fill_poly([(x, y), (x + 150, y), (x + 92, y + 34), (x, y + 44)], tan)
    fill_poly([(x + w, y + h), (x + 300, y + h), (x + 372, y + 60),
               (x + w, y + 52)], tan)
    for x0, y0, x1 in ((30, 70, 52), (330, 26, 352), (250, 80, 272)):
        thick_line(x + x0, y + y0, x + x1, y + y0, 2.5, (70, 130, 175))
    # a naval mine in the water
    fill_disc(x + 120, y + 76, 5, (20, 22, 28))
    for a in (0.0, 1.57, 3.14, 4.71):
        thick_line(x + 120, y + 76, x + 120 + 8 * cos(a), y + 76 + 8 * sin(a),
                   2, (20, 22, 28))
    # supertanker
    fill_poly([(x + 150, y + 62), (x + 330, y + 62), (x + 316, y + 78),
               (x + 164, y + 78)], (30, 34, 44))
    fill_poly([(x + 164, y + 78), (x + 316, y + 78), (x + 310, y + 84),
               (x + 170, y + 84)], (160, 40, 40))
    fill_rect(x + 158, y + 55, x + 322, y + 62, (90, 96, 108))
    for dx, c in ((168, (200, 90, 50)), (192, (60, 130, 90)), (216, (210, 160, 60))):
        fill_rect(x + dx, y + 41, x + dx + 22, y + 55, c)
    fill_rect(x + 292, y + 36, x + 316, y + 55, (238, 240, 244))
    fill_rect(x + 295, y + 40, x + 313, y + 44, (40, 80, 120))
    fill_rect(x + 268, y + 42, x + 278, y + 55, (40, 44, 54))
    fill_disc(x + 273, y + 34, 4, (150, 156, 166))
    fill_disc(x + 279, y + 27, 5.5, (150, 156, 166))
    # flames over the cargo
    for fx in (179, 227):
        fill_poly([(x + fx, y + 42), (x + fx - 7, y + 28), (x + fx - 2, y + 18),
                   (x + fx + 3, y + 10), (x + fx + 6, y + 22), (x + fx + 9, y + 30),
                   (x + fx + 5, y + 42)], (232, 110, 40))
        fill_poly([(x + fx + 1, y + 42), (x + fx - 3, y + 31), (x + fx + 1, y + 24),
                   (x + fx + 4, y + 19), (x + fx + 5, y + 29), (x + fx + 6, y + 42)],
                  (248, 196, 70))
    # price tag
    fill_poly([(x + 372, y + 20), (x + 388, y + 8), (x + 388, y + 32)], (248, 248, 246))
    fill_rect(x + 388, y + 8, x + 446, y + 32, (248, 248, 246))
    fill_disc(x + 394, y + 20, 2.5, NAVY)
    draw_text(x + 402, y + 11, "$92", 16, NAVY_TX, bold=True)
    border(x, y, w, h, NAVY, 2)


# ------------------------------------------------------------------- page
def kicker(x, y, label, color):
    fill_rect(x, y + 1, x + 10, y + 11, color)
    draw_text(x + 18, y, label, 12.5, color, bold=True)


def render_page():
    MX = 36
    # masthead: navy band, gold title
    fill_rect(0, 0, W, 110, NAVY)
    fill_rect(0, 110, W, 113, GOLD)
    draw_text(512, 16, "THE WORLD", 58, GOLD, bold=True, align='center', tracking=3)
    draw_text(512, 84, "THE WORLD'S NEWS · ONE DAY · ONE IMAGE", 12.5, PAPER,
              align='center', tracking=1)
    draw_text(MX, 86, "VOL. I — No. 19", 10, (200, 205, 220))
    draw_text(988, 86, "ONE-IMAGE EDITION", 10, (200, 205, 220), align='right')
    # dateline strip
    fill_rect(0, 150, W, 153, RED)
    draw_text(512, 119, "THURSDAY, 19 NOVEMBER 2026", 25, RED, bold=True, align='center')
    draw_text(MX, 126, "APEC SUMMIT DAY", 10.5, NAVY_TX, bold=True)
    draw_text(988, 126, "SHENZHEN · BERLIN · HORMUZ", 10.5, NAVY_TX, bold=True,
              align='right')
    # lead story
    fill_rect(MX, 165, MX + 10, 175, RED)
    draw_text(MX + 18, 163, "LEAD STORY — THE APEC SUMMIT · SHENZHEN, CHINA", 13.5,
              RED, bold=True)
    draw_text(MX, 186, "A FIRST IN SHENZHEN:", 39, NAVY_TX, bold=True)
    draw_text(MX, 234, "TRUMP, XI AND PUTIN AT ONE TABLE", 39, NAVY_TX, bold=True)
    deck = ("The first three-way meeting of American, Chinese and Russian "
            "leaders, held at Kylin Villa on the sidelines of the APEC "
            "summit, ended with a joint pledge on nuclear war.")
    dy = 292
    for line in wrap_words(deck, 14.5, 952):
        draw_text(MX, dy, line, 14.5, GREY)
        dy += 20
    lead_illustration(MX, 344, 470, 246)
    lead_body = (
        "Donald Trump, Xi Jinping and Vladimir Putin met in Shenzhen on "
        "Thursday — the first time the leaders of the United States, China "
        "and Russia have sat down together. Their joint declaration said "
        "that 'a nuclear war cannot be won and must never be fought'. They "
        "agreed to open a dialogue on reducing nuclear risks and preventing "
        "proliferation, pledged reform of the United Nations, and planned "
        "to increase the supply of refined petroleum products. The "
        "Trump–Putin bilateral lasted about 42 minutes; the trilateral "
        "session ran about 81 minutes. It was Putin's return to APEC after "
        "a nine-year absence. Together the three men control about 90% of "
        "the world's nuclear weapons.")
    draw_paragraph(524, 344, lead_body, 12, INK, 17.2, [(0, 464)])
    # middle row: Berlin and Hormuz
    fill_rect(MX, 606, 988, 608, RULE)
    kicker(MX, 616, "BERLIN — THE COALITION OF THE WILLING", BLUE_K)
    kicker(524, 616, "STRAIT OF HORMUZ — THE GULF WAR", ORNG_K)
    draw_text(MX, 636, "EUROPE'S ALLIES GATHER", 21.5, NAVY_TX, bold=True)
    draw_text(MX, 663, "IN BERLIN FOR UKRAINE", 21.5, NAVY_TX, bold=True)
    draw_text(524, 636, "IRAN SAYS TANKERS HIT", 21.5, NAVY_TX, bold=True)
    draw_text(524, 663, "MINES IN THE HORMUZ STRAIT", 21.5, NAVY_TX, bold=True)
    berlin_banner(MX, 692, 465, 88)
    hormuz_banner(524, 692, 464, 88)
    berlin_body = (
        "The 'Coalition of the Willing', more than 30 countries backing "
        "Ukraine, met in Berlin: Chancellor Friedrich Merz, President "
        "Emmanuel Macron, Prime Minister Andy Burnham, President Volodymyr "
        "Zelenskiy, NATO chief Mark Rutte and US envoys Steve Witkoff and "
        "Jared Kushner. The European Commission proposed a €45 billion "
        "loan for Ukraine for 2027. They called for a winter ceasefire on "
        "attacks on energy infrastructure; Macron urged reopening the "
        "question of Ukraine's NATO membership.")
    draw_paragraph(MX, 788, berlin_body, 11, INK, 14.0, [(0, 465)])
    hormuz_body = (
        "Iran's Revolutionary Guards said two supertankers hit naval mines "
        "in the strait on Thursday and caught fire. Houthi missiles were "
        "fired at Riyadh, Saudi Arabia. Brent crude traded near $92 a "
        "barrel, and shipping through the strait has fallen to about 2.3 "
        "ships a day, against 68 a day before the war (IMF PortWatch).")
    draw_paragraph(524, 788, hormuz_body, 11, INK, 14.0, [(0, 464)])
    # bottom strip: Kim item and the day in numbers
    fill_rect(MX, 934, 988, 936, RULE)
    flag_us(MX, 942, 46, 27)
    flag_nk(MX, 973, 46, 27)
    draw_text(98, 940, "NORTH KOREA — WASHINGTON", 10.5, TEAL_K, bold=True)
    draw_text(98, 954, "TRUMP: 'I WILL MEET KIM JONG-UN'", 19, NAVY_TX, bold=True)
    draw_text(98, 980, "Donald Trump told NBC News he will meet North Korea's "
              "Kim Jong-un 'at some point'.", 10.3, INK)
    fill_rect(692, 940, 988, 1000, NAVY)
    border(692, 940, 296, 60, GOLD, 2)
    draw_text(840, 945, "THE DAY IN NUMBERS", 10, GOLD, bold=True, align='center')
    draw_text(840, 958, "BRENT $92 A BARREL", 17, PAPER, bold=True, align='center')
    draw_text(840, 982, "HORMUZ: 2.3 SHIPS A DAY — DOWN FROM 68", 9.8, (216, 222, 235),
              align='center')
    # footer
    fill_rect(MX, 1006, 988, 1008, RULE)
    draw_text(512, 1010, "ALL STORIES FROM THURSDAY 19 NOVEMBER 2026 · "
              "COMPILED FROM WIRE REPORTS", 9.5, GREY, align='center')


# -------------------------------------------------------------------- png
def write_png(path):
    raw = bytearray()
    for yy in range(H):
        raw.append(0)
        raw += fb[yy * W * 3:(yy + 1) * W * 3]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data
                + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', comp)
           + chunk(b'IEND', b''))
    with open(path, 'wb') as fh:
        fh.write(png)
    return len(png)


def main(argv):
    out = argv[1] if len(argv) > 1 else '/output/entry.png'
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    render_page()
    n = write_png(out)
    print(f"wrote {out} ({n} bytes)")


if __name__ == '__main__':
    main(sys.argv)
