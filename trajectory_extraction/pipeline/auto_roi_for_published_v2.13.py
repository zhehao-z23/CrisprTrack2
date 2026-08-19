#!/usr/bin/env python3
"""
auto_roi_for_published_v2.13.py — Pixel size derived from .tif metadata.

Usage:
    python3 auto_roi_for_published_v2.13.py /path/to/image_Nucleus.tif \
        --reference-channel purple

Changes from v2.12:
  • PIXEL_SIZE_UM is no longer a hard-coded constant.  It is derived at
    runtime from the XResolution TIFF tag of the input file, interpreted
    via the ImageJ ImageDescription unit annotation (preferred) or the
    TIFF ResolutionUnit tag.  The value is the reciprocal of pixel width
    (or height) in microns, i.e. pixels per µm.
  • read_pixel_size_from_tif() added for metadata parsing.
  • _INTER_FRAME_MAX_PX, _INTER_FRAME_MAX_PX_RED, _REFERENCE_PROX_MAX_PX are
    computed inside main() after reading the metadata, then stored as
    module-level globals so all helper functions can access them unchanged.

Outputs (same naming as v2.8 / v2.10 / v2.11 / v2.12):
    RoiSet_{reference-channel}.zip
    Nucleus_masks.tif
    G_loci{N}_traj_rela2wholeimg.csv
    P_loci{N}_traj_rela2wholeimg.csv   (omitted if no unique match found)
    R_loci{N}_traj_rela2wholeimg.csv   (omitted if no unique match found)
"""

import argparse
import sys
import csv
import json
import struct
import zipfile
from collections import defaultdict
import numpy as np
from pathlib import Path
from scipy import ndimage
from scipy.optimize import linear_sum_assignment
import coordinate_system

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8', errors='replace')

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PARAMETERS  —  edit these to tune the analysis                         ║
# ╚══════════════════════════════════════════════════════════════════════════╝

REFERENCE_SEED_K = {
    'green':  2.0,
    'red':    0.5,
    'purple': 1.645,
}

REFERENCE_TRACKING_K = {
    'green':  2.0,
    'red':    0.5,
    'purple': 0.5,
}

TARGET_TRACKING_K = {
    'green':  2.0,
    'red':    0.5,
    'purple': 0.5,
}

REFERENCE_MASK_OCCUPANCY_FRACTION = 0.50
REFERENCE_CONTAINMENT_FRACTION = 1.0
REFERENCE_EDGE_WIDTH_PX = 3.0
REFERENCE_MAX_EDGE_FRACTION = 0.10

CHANNELS = ('green', 'red', 'purple')
CHANNEL_PREFIX = {'green': 'G', 'red': 'R', 'purple': 'P'}

# Nucleus boundary detection: Gaussian pre-blur sigma (px) before Otsu thresholding.
NUCLEUS_SIGMA = 2.0

# Maximum fraction of tracked frames allowed to be outside the nucleus mask
# before a locus is rejected.  Default 0.10 = up to 10 % of frames may be outside.
NUCLEUS_OUTSIDE_FRAC = 0.10

# Drift-correction fill detection: a pixel is a fill candidate if its value is
# below FILL_RATIO × (75th-percentile of the image).  Only border-connected
# candidates are excluded.
FILL_RATIO = 0.85

MIN_SPOT_PX = 10

N_MAX        = 5
PADDING      = 20   # pixels added around the trajectory bounding box on all sides
ADJACENCY_PX = 30

# ── Physical-unit parameters for purple/red tracking ─────────────────────────
# PIXEL_SIZE_UM (px/µm) is NOT pre-defined here; it is read from .tif metadata
# in main() via read_pixel_size_from_tif() and stored as a module-level global.
PIXEL_SIZE_UM = None  # set in main() from image metadata

# Maximum frame-to-frame drift allowed when tracking purple/red (nm).
INTER_FRAME_MAX_NM     = 500
INTER_FRAME_MAX_NM_RED = 750   # relaxed for red: 90th-percentile observed jump ~580 nm

# Maximum distance from the reference spot in the same frame for target channels (µm).
REFERENCE_PROX_MAX_UM = 3.0

# DSB v5.2: Purple only gates the Red search support and supplies the canonical
# allele identity.  Red trajectories themselves are linked by Red continuity.
DSB_RED_HARVEST_RADIUS_UM = 2.5
DSB_RED_MIN_TRACK_POINTS = 5
DSB_RED_MIN_SHARED_FRAMES = 5
DSB_RED_MIN_MOVIE_COVERAGE_FRACTION = 0.25
DSB_RED_UNIQUENESS_MARGIN_PX = 1.0
DSB_RED_MAX_MISSING_FRAMES = 1

# Give up seeding a purple/red trajectory if no match is found in first N frames.
SEED_MAX_FRAME = 5

# Maximum component area (px) in the union-mask seed step before adaptive
# k-elevation is triggered.  Components larger than this are treated as merged
# spots and re-examined at higher k values.
MAX_BLOB_PX = 120

# ── Derived pixel-space limits (computed in main() after reading metadata) ────
_INTER_FRAME_MAX_PX     = None  # set in main()
_INTER_FRAME_MAX_PX_RED = None  # set in main()
_REFERENCE_PROX_MAX_PX  = None  # set in main()

# k values tried (in order) when a large blob is found; must be > base k.
_ADAPTIVE_K_STEPS = [1.0, 1.5, 2.0]

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  IMPLEMENTATION — helpers unchanged from v2.8                           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def load_stack(path: Path) -> np.ndarray:
    """Load a multi-frame TIFF → float32 array (frames, height, width)."""
    from PIL import Image
    img = Image.open(str(path))
    frames = []
    try:
        i = 0
        while True:
            img.seek(i)
            frames.append(np.array(img, dtype=np.float32))
            i += 1
    except EOFError:
        pass
    return np.stack(frames)


def read_pixel_size_from_tif(path: Path) -> float:
    """
    Read XResolution from TIFF metadata and return pixels per µm.

    Interpretation priority:
      1. ImageJ ImageDescription (tag 270): if "unit=micron" (or equivalent)
         is present, XResolution is already in px/µm.
      2. TIFF ResolutionUnit (tag 296): converts XResolution from px/cm
         (ResolutionUnit=3) or px/inch (ResolutionUnit=2) to px/µm.
      3. ResolutionUnit=1 (no absolute unit) with no ImageJ annotation:
         XResolution is assumed to be in px/µm.

    Raises ValueError if the pixel size cannot be determined.
    """
    from PIL import Image
    img = Image.open(str(path))
    tags = getattr(img, 'tag_v2', {})

    # --- XResolution (tag 282) ---
    x_res_raw = tags.get(282)
    if x_res_raw is None:
        raise ValueError(
            f"No XResolution tag found in {path.name}; "
            "cannot derive pixel size from metadata.")
    if hasattr(x_res_raw, '__float__'):
        x_res = float(x_res_raw)
    elif isinstance(x_res_raw, (list, tuple)):
        val = x_res_raw[0]
        x_res = float(val) if hasattr(val, '__float__') else float(val[0]) / float(val[1])
    else:
        x_res = float(x_res_raw)
    if x_res == 0.0:
        raise ValueError(f"XResolution is zero in {path.name}.")

    # --- ResolutionUnit (tag 296; default 2 = inch per TIFF spec) ---
    res_unit_raw = tags.get(296, 2)
    if isinstance(res_unit_raw, (list, tuple)):
        res_unit = int(res_unit_raw[0])
    else:
        res_unit = int(res_unit_raw)

    # --- ImageDescription (tag 270) — check for ImageJ unit annotation ---
    img_desc_raw = tags.get(270, '')
    if isinstance(img_desc_raw, bytes):
        img_desc = img_desc_raw.decode('latin-1', errors='replace')
    elif isinstance(img_desc_raw, (list, tuple)):
        img_desc = str(img_desc_raw[0]) if img_desc_raw else ''
    else:
        img_desc = str(img_desc_raw)

    ij_unit = None
    for line in img_desc.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        stripped = line.strip()
        if stripped.lower().startswith('unit='):
            ij_unit = stripped.split('=', 1)[1].strip().lower()
            break

    # --- Convert XResolution to px/µm ---
    _UM = {'micron', 'microns', 'um', 'µm', 'μm', 'micrometer', 'micrometers',
           'micrometre', 'micrometres'}
    _NM = {'nm', 'nanometer', 'nanometers', 'nanometre', 'nanometres'}
    _CM = {'cm', 'centimeter', 'centimeters', 'centimetre', 'centimetres'}

    if ij_unit in _UM:
        return x_res                 # XResolution is already px/µm
    elif ij_unit in _NM:
        return x_res / 1000.0        # px/nm → px/µm
    elif ij_unit in _CM or res_unit == 3:
        return x_res / 1e4           # px/cm → px/µm
    elif res_unit == 2:
        return x_res / 25400.0       # px/inch → px/µm
    elif res_unit == 1:
        # No absolute unit in TIFF tags and no ImageJ annotation;
        # assume XResolution is in px/µm (common for microscopy files).
        return x_res
    else:
        raise ValueError(
            f"Cannot determine pixel unit for {path.name}: "
            f"ResolutionUnit={res_unit}, ImageJ unit tag='{ij_unit}'. "
            "Check your TIFF metadata.")


def compute_valid_mask(image: np.ndarray) -> np.ndarray:
    """
    Detect drift-correction fill pixels in a single 2D image (one frame or average).

    Fill values vary per frame (0, 13, 52, 76 … ADU) and are always well below
    true background.  Algorithm: threshold at 75th-percentile × FILL_RATIO, label
    connected components, keep only border-connected ones, return complement.
    """
    H, W = image.shape
    bg_ref     = float(np.percentile(image, 75))
    low_thresh = bg_ref * FILL_RATIO
    is_candidate = image < low_thresh
    labeled, _ = ndimage.label(is_candidate)
    border_labels = set()
    for edge in (labeled[0, :], labeled[-1, :], labeled[:, 0], labeled[:, -1]):
        border_labels.update(int(v) for v in edge if v > 0)
    if not border_labels:
        return np.ones((H, W), dtype=bool)
    fill_mask = np.zeros((H, W), dtype=bool)
    for bl in border_labels:
        fill_mask |= (labeled == bl)
    return ~fill_mask


def otsu_threshold(image: np.ndarray) -> float:
    """Compute Otsu's optimal binary threshold (maximises between-class variance)."""
    hist, bin_edges = np.histogram(image.flatten(), bins=256)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    total   = float(hist.sum())
    sum_all = float(np.dot(hist, bin_centers))
    w0, sum0, best_thresh, best_var = 0.0, 0.0, bin_centers[0], 0.0
    for i in range(len(hist)):
        w0 += hist[i]
        if w0 == 0:
            continue
        w1 = total - w0
        if w1 == 0:
            break
        sum0 += hist[i] * bin_centers[i]
        mu0   = sum0 / w0
        mu1   = (sum_all - sum0) / w1
        var_between = (w0 / total) * (w1 / total) * (mu0 - mu1) ** 2
        if var_between > best_var:
            best_var    = var_between
            best_thresh = bin_centers[i]
    return best_thresh


def detect_nucleus_frames(nucleus_stack: np.ndarray) -> list:
    """
    Per-frame nucleus mask: Gaussian blur + Otsu + hole filling.
    Returns list of 2D bool arrays or None where detection failed.
    None frames are skipped in nucleus check (benefit of the doubt).
    """
    masks, n_skipped = [], 0
    for t, frame in enumerate(nucleus_stack):
        valid    = compute_valid_mask(frame)
        smoothed = ndimage.gaussian_filter(frame.astype(np.float32), sigma=NUCLEUS_SIGMA)
        thresh   = otsu_threshold(smoothed[valid])
        p5 = float(np.percentile(smoothed[valid], 5))
        if thresh < p5:
            n_skipped += 1
            masks.append(None)
            continue
        binary  = ndimage.binary_fill_holes((smoothed > thresh) & valid)
        labeled, n_comp = ndimage.label(binary)
        if n_comp == 0:
            n_skipped += 1
            masks.append(None)
            continue
        sizes = [(int(np.sum(labeled == i)), i) for i in range(1, n_comp + 1)]
        largest_idx = max(sizes, key=lambda x: x[0])[1]
        masks.append(labeled == largest_idx)
    if n_skipped > 0:
        print(f"    Note: {n_skipped} frame(s) near-unimodal → nucleus undetectable, "
              f"skipped in signal check")
    return masks


def save_nucleus_masks_tiff(masks: list, H: int, W: int, path: Path):
    """Save per-frame nucleus masks as multi-frame binary TIFF (uint8, 0/255)."""
    from PIL import Image
    imgs = []
    for m in masks:
        frame = (m.astype(np.uint8) * 255) if m is not None else np.zeros((H, W), dtype=np.uint8)
        imgs.append(Image.fromarray(frame))
    imgs[0].save(str(path), save_all=True, append_images=imgs[1:])


def point_in_mask(y: float, x: float, mask: np.ndarray) -> bool:
    """Return True if pixel (y, x) falls inside the binary nucleus mask."""
    H, W = mask.shape
    yi, xi = int(round(y)), int(round(x))
    if 0 <= yi < H and 0 <= xi < W:
        return bool(mask[yi, xi])
    return False


def detect_signal_clusters(
    avg: np.ndarray,
    k: float,
    min_px: int,
    n_max: int,
    nucleus_mask: np.ndarray,
    edge_width_px: float,
    maximum_edge_fraction: float,
) -> tuple[list, dict]:
    """
    Threshold the time-averaged image at mean + k×std, find connected components
    >= min_px pixels.  Returns up to n_max cluster dicts sorted by mean intensity
    (brightest first).  Each dict: centroid (y,x), bbox, intensity, size.
    """
    valid = compute_valid_mask(avg)
    mean = float(avg[valid].mean())
    standard_deviation = float(avg[valid].std())
    threshold = mean + k * standard_deviation
    labeled, component_count = ndimage.label((avg > threshold) & valid)
    distance_inside = ndimage.distance_transform_edt(nucleus_mask)
    clusters = []
    component_audit = []
    area_eligible = 0
    containment_rejected = 0
    edge_rejected = 0
    for label_id in range(1, component_count + 1):
        component = labeled == label_id
        size = int(component.sum())
        if size < min_px:
            component_audit.append({
                'component_id': int(label_id),
                'size_px': size,
                'decision': 'REJECT_MINIMUM_AREA',
            })
            continue
        area_eligible += 1
        inside_fraction = float((component & nucleus_mask).sum() / size)
        if inside_fraction < REFERENCE_CONTAINMENT_FRACTION:
            containment_rejected += 1
            component_audit.append({
                'component_id': int(label_id),
                'size_px': size,
                'inside_fraction': inside_fraction,
                'decision': 'REJECT_NOT_FULLY_CONTAINED',
            })
            continue
        edge_fraction = float((distance_inside[component] <= edge_width_px).mean())
        if edge_fraction > maximum_edge_fraction:
            edge_rejected += 1
            component_audit.append({
                'component_id': int(label_id),
                'size_px': size,
                'inside_fraction': inside_fraction,
                'edge_fraction': edge_fraction,
                'decision': 'REJECT_EDGE_BAND_FRACTION',
            })
            continue
        cy, cx = ndimage.center_of_mass(avg, labeled, label_id)
        rows, columns = np.where(component)
        candidate = {
            'component_id': int(label_id),
            'centroid': (float(cy), float(cx)),
            'bbox': (
                int(rows.min()), int(columns.min()),
                int(rows.max()), int(columns.max()),
            ),
            'intensity': float(avg[component].mean()),
            'size': size,
            'inside_fraction': inside_fraction,
            'edge_fraction': edge_fraction,
        }
        clusters.append(candidate)
        component_audit.append({
            'component_id': int(label_id),
            'size_px': size,
            'inside_fraction': inside_fraction,
            'edge_fraction': edge_fraction,
            'mean_intensity': candidate['intensity'],
            'centroid_y_px': candidate['centroid'][0],
            'centroid_x_px': candidate['centroid'][1],
            'decision': 'ELIGIBLE_BEFORE_TOP_N',
        })
    clusters.sort(key=lambda cluster: cluster['intensity'], reverse=True)
    returned = clusters[:n_max]
    audit = {
        'threshold_mean': mean,
        'threshold_std': standard_deviation,
        'seed_k': float(k),
        'threshold': float(threshold),
        'minimum_area_px': int(min_px),
        'global_area_eligible_components': int(area_eligible),
        'containment_fraction_required': REFERENCE_CONTAINMENT_FRACTION,
        'containment_rejected_components': int(containment_rejected),
        'edge_width_px': float(edge_width_px),
        'maximum_edge_fraction': float(maximum_edge_fraction),
        'edge_rejected_components': int(edge_rejected),
        'survivors_before_top_n': int(len(clusters)),
        'top_n': int(n_max),
        'all_threshold_components': component_audit,
        'returned_components': [
            {
                'rank': rank,
                'component_id': cluster['component_id'],
                'centroid_y_px': cluster['centroid'][0],
                'centroid_x_px': cluster['centroid'][1],
                'size_px': cluster['size'],
                'mean_intensity': cluster['intensity'],
                'inside_fraction': cluster['inside_fraction'],
                'edge_fraction': cluster['edge_fraction'],
            }
            for rank, cluster in enumerate(returned, start=1)
        ],
    }
    return returned, audit


def component_sizes_and_centroids(
    labeled: np.ndarray, n_components: int, weights: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Return component sizes and centroids without copying one full image per label."""
    if n_components == 0:
        return np.empty(0, dtype=np.int64), np.empty((0, 2), dtype=float)
    labels = np.arange(1, n_components + 1)
    sizes = np.bincount(labeled.ravel(), minlength=n_components + 1)[1:]
    if weights is None:
        weights = np.ones(labeled.shape, dtype=np.float32)
    centroids = np.asarray(ndimage.center_of_mass(weights, labeled, labels), dtype=float)
    return sizes, centroids


def track_spot_indexed(stack: np.ndarray, centroid_avg: tuple, k: float) -> list:
    """
    Track a signal spot across all frames.
    Returns (frame_index, y, x) triples; frames with no match within ADJACENCY_PX
    are omitted.
    """
    cy0, cx0 = centroid_avg
    positions = []
    for t, frame in enumerate(stack):
        valid  = compute_valid_mask(frame)
        m, s   = frame[valid].mean(), frame[valid].std()
        labeled, n = ndimage.label((frame > (m + k * s)) & valid)
        best, best_d = None, ADJACENCY_PX
        _, centroids = component_sizes_and_centroids(labeled, n, weights=frame)
        for cy, cx in centroids:
            d = np.hypot(cy - cy0, cx - cx0)
            if d < best_d:
                best_d, best = d, (cy, cx)
        if best:
            positions.append((t, best[0], best[1]))
    return positions


def compute_roi_from_trajectory(indexed_pos: list, H: int, W: int) -> tuple:
    """
    Compute ROI as the trajectory bounding box expanded by PADDING on all sides,
    clipped to image bounds.  Returns (top, left, bottom, right).
    """
    ys = [p[1] for p in indexed_pos]
    xs = [p[2] for p in indexed_pos]
    top    = max(0, int(min(ys)) - PADDING)
    left   = max(0, int(min(xs)) - PADDING)
    bottom = min(H, int(max(ys)) + PADDING + 1)
    right  = min(W, int(max(xs)) + PADDING + 1)
    return top, left, bottom, right


def track_channel_in_roi(stack: np.ndarray, roi: tuple,
                          reference_indexed_pos: list, reference_centroid_avg: tuple,
                          k: float, inter_frame_max_px: float = None) -> list:
    """
    Track a target-channel spot within a fixed ROI across all frames.
    Used for non-overlapping (singleton) loci, anchored to the reference channel.

    Primary linking: candidate must be within inter_frame_max_px of last position
    AND within _REFERENCE_PROX_MAX_PX of the reference spot.

    Fallback (when primary yields nothing): accept the candidate closest to the
    reference spot, as long as it is within _REFERENCE_PROX_MAX_PX.  This handles highly
    mobile loci whose frame-to-frame displacement exceeds inter_frame_max_px but
    whose signal stays near the reference anchor.
    """
    if inter_frame_max_px is None:
        inter_frame_max_px = _INTER_FRAME_MAX_PX
    top, left, bottom, right = roi
    n_frames = stack.shape[0]
    reference_tracked = {t: (fy, fx) for t, fy, fx in reference_indexed_pos}

    def candidates_in_roi(frame_arr):
        valid  = compute_valid_mask(frame_arr)
        m, s   = frame_arr[valid].mean(), frame_arr[valid].std()
        labeled, n = ndimage.label((frame_arr > (m + k * s)) & valid)
        found = []
        sizes, centroids = component_sizes_and_centroids(labeled, n)
        for size, (cy, cx) in zip(sizes, centroids):
            if int(size) < MIN_SPOT_PX:
                continue
            if top <= cy < bottom and left <= cx < right:
                found.append((cy, cx))
        return found

    seed_frame = None
    last_pos   = None
    positions  = []

    for f in range(min(SEED_MAX_FRAME, n_frames)):
        cands = candidates_in_roi(stack[f])
        if not cands:
            continue
        ref_y, ref_x = reference_tracked.get(f, reference_centroid_avg)
        best = min(cands, key=lambda p: np.hypot(p[0] - ref_y, p[1] - ref_x))
        seed_frame = f
        last_pos   = best
        positions.append((f, best[0], best[1]))
        break

    if seed_frame is None:
        return []

    for f in range(seed_frame + 1, n_frames):
        cands = candidates_in_roi(stack[f])
        ref_y, ref_x = reference_tracked.get(f, reference_centroid_avg)

        # Primary: inter-frame constraint + reference proximity
        cands_primary = [(cy, cx) for cy, cx in cands
                          if np.hypot(cy - last_pos[0], cx - last_pos[1]) <= inter_frame_max_px
                          and np.hypot(cy - ref_y, cx - ref_x) <= _REFERENCE_PROX_MAX_PX]
        if cands_primary:
            best = min(cands_primary,
                       key=lambda p: np.hypot(p[0] - last_pos[0], p[1] - last_pos[1]))
            last_pos = best
            positions.append((f, best[0], best[1]))
            continue

        # Fallback: reference proximity only (handles highly mobile loci)
        cands_fallback = [(cy, cx) for cy, cx in cands
                          if np.hypot(cy - ref_y, cx - ref_x) <= _REFERENCE_PROX_MAX_PX]
        if cands_fallback:
            best = min(cands_fallback, key=lambda p: np.hypot(p[0] - ref_y, p[1] - ref_x))
            last_pos = best
            positions.append((f, best[0], best[1]))

    return positions


def save_trajectory_csv(indexed_pos: list, path: Path):
    """
    Save a trajectory as a CSV file with columns frame, x_nm, y_nm.
    - frame: 1-based
    - x_nm, y_nm: position in nanometres, 1-indexed pixel convention
    """
    with open(str(path), 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['frame', 'x_nm', 'y_nm'])
        for frame_idx, y, x in indexed_pos:
            pixel_size_nm = 1000.0 / PIXEL_SIZE_UM
            x_nm = float(coordinate_system.image_px_to_automatic_nm(x, pixel_size_nm))
            y_nm = float(coordinate_system.image_px_to_automatic_nm(y, pixel_size_nm))
            writer.writerow([frame_idx + 1, f'{x_nm:.2f}', f'{y_nm:.2f}'])


def write_roi_file(path: Path, top: int, left: int, bottom: int, right: int):
    """Write a minimal ImageJ binary rectangle .roi file (version 228)."""
    header = bytearray(64)
    header[0:4] = b'Iout'
    struct.pack_into('>H', header, 4,  228)
    header[6] = 1
    struct.pack_into('>H', header, 8,  max(0, top))
    struct.pack_into('>H', header, 10, max(0, left))
    struct.pack_into('>H', header, 12, max(0, bottom))
    struct.pack_into('>H', header, 14, max(0, right))
    path.write_bytes(bytes(header))


def save_roi_zip(rois: list, zip_path: Path, out_dir: Path):
    """Write a list of ROI dicts to a zip file. Does nothing if rois is empty."""
    if not rois:
        return
    tmp_files = []
    for roi in rois:
        name = f"loci{roi['label']}.roi"
        p    = out_dir / name
        write_roi_file(p, roi['top'], roi['left'], roi['bottom'], roi['right'])
        tmp_files.append((name, p))
    with zipfile.ZipFile(str(zip_path), 'w') as zf:
        for name, p in tmp_files:
            zf.write(str(p), name)
    for _, p in tmp_files:
        p.unlink()


def roi_dict(t, l, b, r, label):
    return {'top': t, 'left': l, 'bottom': b, 'right': r, 'label': label}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  HELPERS — v2.10 joint seeding (unchanged)                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _rois_overlap(roi1: tuple, roi2: tuple) -> bool:
    """Return True if two (top, left, bottom, right) rectangles share any pixel."""
    t1, l1, b1, r1 = roi1
    t2, l2, b2, r2 = roi2
    return t1 < b2 and t2 < b1 and l1 < r2 and l2 < r1


def find_overlap_groups(accepted: list) -> list:
    """
    Union-find connected components of overlapping ROIs.
    Returns list of groups (each a list of indices into accepted).
    """
    n = len(accepted)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(n):
        for j in range(i + 1, n):
            if _rois_overlap(accepted[i][2], accepted[j][2]):
                union(i, j)

    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return list(groups.values())


def compute_union_mask(rois: list, H: int, W: int) -> np.ndarray:
    """Boolean (H×W) mask = union of all (top, left, bottom, right) ROI rectangles."""
    mask = np.zeros((H, W), dtype=bool)
    for (t, l, b, r) in rois:
        mask[t:b, l:r] = True
    return mask


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  NEW HELPERS — v2.11 adaptive k seed detection                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _find_candidates_adaptive(frame_arr: np.ndarray, union_mask: np.ndarray,
                               base_k: float, frame_idx: int) -> list:
    """
    Detect signal candidates in frame_arr whose centroid falls inside union_mask.

    Each component detected at base_k is classified:
      • area <= MAX_BLOB_PX — kept directly; detection k = base_k.
      • area >  MAX_BLOB_PX — likely a merged blob; try to split by re-examining
        the blob's own pixels at progressively higher thresholds (k in
        _ADAPTIVE_K_STEPS).  Only pixels belonging to this particular blob are
        affected; all other components are unchanged.

    Splitting logic (for each k_try in _ADAPTIVE_K_STEPS):
      1. Apply k_try threshold to the whole frame; label connected components.
      2. Identify sub-components whose pixels overlap this blob's mask.
      3. If no sub-components survive (blob fully disappeared or all fragments
         below MIN_SPOT_PX) → immediate fallback: use original centroid at base_k.
      4. If all valid sub-components have area <= MAX_BLOB_PX → success: replace
         the blob with those sub-components, each carrying k_try.
      5. Otherwise → some sub-components still too large; try next k_try.
      6. If k_try exhausted at 2.0 without success → fallback to original centroid.

    Returns list of (cy, cx, k_detected).
    """
    H, W = union_mask.shape
    valid = compute_valid_mask(frame_arr)
    m = float(frame_arr[valid].mean())
    s = float(frame_arr[valid].std())

    binary_base = (frame_arr > m + base_k * s) & valid
    labeled_base, n_base = ndimage.label(binary_base)

    result = []

    for idx in range(1, n_base + 1):
        comp_mask = (labeled_base == idx)
        area = int(comp_mask.sum())
        if area < MIN_SPOT_PX:
            continue
        cy, cx = ndimage.center_of_mass(comp_mask)
        yi, xi = int(round(cy)), int(round(cx))
        if not (0 <= yi < H and 0 <= xi < W and union_mask[yi, xi]):
            continue

        if area <= MAX_BLOB_PX:
            result.append((cy, cx, base_k))
            continue

        # ── Large blob: try adaptive splitting ───────────────────────────────
        split_placed = False
        for k_try in _ADAPTIVE_K_STEPS:
            binary_high = (frame_arr > m + k_try * s) & valid
            labeled_high, _ = ndimage.label(binary_high)

            # Sub-component labels from the higher threshold that overlap this blob
            sub_indices = set(int(v) for v in labeled_high[comp_mask] if v > 0)

            if not sub_indices:
                # Blob fully disappeared at k_try — no point trying larger k
                print(f"      [fr{frame_idx}] Large blob (area={area} px) disappeared "
                      f"at k={k_try} — fallback (k={base_k})")
                result.append((cy, cx, base_k))
                split_placed = True
                break

            # Collect valid sub-candidates
            sub_cands = []
            for sub_idx in sub_indices:
                sub_mask = (labeled_high == sub_idx)
                sub_area = int(sub_mask.sum())
                if sub_area < MIN_SPOT_PX:
                    continue
                sub_cy, sub_cx = ndimage.center_of_mass(sub_mask)
                sub_yi = int(round(sub_cy))
                sub_xi = int(round(sub_cx))
                if not (0 <= sub_yi < H and 0 <= sub_xi < W
                        and union_mask[sub_yi, sub_xi]):
                    continue
                sub_cands.append((sub_cy, sub_cx, sub_area))

            if not sub_cands:
                # All fragments below MIN_SPOT_PX or outside mask
                print(f"      [fr{frame_idx}] Large blob (area={area} px) fragmented "
                      f"below MIN_SPOT_PX at k={k_try} — fallback (k={base_k})")
                result.append((cy, cx, base_k))
                split_placed = True
                break

            if all(sc[2] <= MAX_BLOB_PX for sc in sub_cands):
                # Successfully split
                print(f"      [fr{frame_idx}] Large blob (area={area} px) → "
                      f"{len(sub_cands)} sub-component(s) at k={k_try} "
                      f"(areas: {[sc[2] for sc in sub_cands]})")
                for sub_cy, sub_cx, _ in sub_cands:
                    result.append((sub_cy, sub_cx, k_try))
                split_placed = True
                break
            # Some sub-components still too large → try next k_try

        if not split_placed:
            # All k steps tried; sub-components still exceed MAX_BLOB_PX
            print(f"      [fr{frame_idx}] Large blob (area={area} px) unsplittable "
                  f"at k={_ADAPTIVE_K_STEPS[-1]} — fallback (k={base_k})")
            result.append((cy, cx, base_k))

    return result


def find_seed_trajectories_in_mask(stack: np.ndarray, union_mask: np.ndarray,
                                    n_seed_frames: int, k: float,
                                    inter_frame_max_px: float = None) -> tuple:
    """
    Find all distinct signal spot trajectories within union_mask across the first
    n_seed_frames frames, using adaptive k detection for large blobs.

    Per frame: _find_candidates_adaptive is called, which returns (cy, cx, k_detected)
    for each candidate.  Normal spots use k=base_k; sub-components from blob splitting
    use k=k_try (the k at which the split succeeded).

    Candidates are linked across consecutive frames with greedy nearest-neighbour
    matching (spatial constraint: inter_frame_max_px; temporal: gap ≤ 1 frame).

    Returns (seed_trajs, seed_ks):
      seed_trajs : list of seed trajectories, each a list of (frame, cy, cx).
      seed_ks    : list of floats, one per trajectory.  seed_ks[i] = k_detected
                   of the last candidate in trajectory i.  Used as the propagation
                   k for that trajectory (so the same threshold applied during
                   seeding is used during propagation).
    """
    if inter_frame_max_px is None:
        inter_frame_max_px = _INTER_FRAME_MAX_PX
    n_frames = min(n_seed_frames, stack.shape[0])

    track_points = []   # track_points[i] = list of (f, cy, cx)
    track_k_last = []   # track_k_last[i] = k_detected of last appended candidate

    for f in range(n_frames):
        cands = _find_candidates_adaptive(stack[f], union_mask, k, f)
        if not cands:
            continue

        # Build scored list: (distance, track_index, candidate_index)
        scored = []
        for ti, tpts in enumerate(track_points):
            last_f, last_y, last_x = tpts[-1]
            if f - last_f > 2:   # allow at most 1-frame gap
                continue
            for ci, (cy, cx, _) in enumerate(cands):
                d = np.hypot(cy - last_y, cx - last_x)
                if d <= inter_frame_max_px:
                    scored.append((d, ti, ci))

        scored.sort()
        matched_tracks, matched_cands = set(), set()
        for d, ti, ci in scored:
            if ti in matched_tracks or ci in matched_cands:
                continue
            cy, cx, k_det = cands[ci]
            track_points[ti].append((f, cy, cx))
            track_k_last[ti] = k_det
            matched_tracks.add(ti)
            matched_cands.add(ci)

        for ci, (cy, cx, k_det) in enumerate(cands):
            if ci not in matched_cands:
                track_points.append([(f, cy, cx)])
                track_k_last.append(k_det)

    return track_points, track_k_last


def match_seeds_to_reference(seed_trajs: list, seed_ks: list,
                             reference_trajs_dict: dict) -> dict:
    """
    Optimal one-to-one matching between seed trajectories and reference loci using
    the Linear Sum Assignment algorithm (minimises total pairwise distance).

    Cost matrix entry [i, j]:
      - Average Euclidean distance (px) between seed_trajs[i] and reference locus j
        across their shared seed frames.
      - Set to a large sentinel (1e9) when there are no shared frames.

    After solving, pairs whose average distance exceeds _REFERENCE_PROX_MAX_PX are
    rejected.

    Returns dict mapping label → (seed_traj, k_propagate), where k_propagate is
    seed_ks[i] for the matched seed trajectory i.
    """
    labels = list(reference_trajs_dict.keys())
    reference_by_frame = {
        label: {f: (y, x) for f, y, x in traj}
        for label, traj in reference_trajs_dict.items()
    }

    n_seeds = len(seed_trajs)
    n_loci  = len(labels)
    if n_seeds == 0 or n_loci == 0:
        return {}

    _INF = 1e9
    cost = np.full((n_seeds, n_loci), _INF)

    for si, seed_traj in enumerate(seed_trajs):
        seed_by_frame = {f: (y, x) for f, y, x in seed_traj}
        for li, label in enumerate(labels):
            shared = [f for f in seed_by_frame if f in reference_by_frame[label]]
            if not shared:
                continue
            cost[si, li] = float(np.mean([
                np.hypot(seed_by_frame[f][0] - reference_by_frame[label][f][0],
                         seed_by_frame[f][1] - reference_by_frame[label][f][1])
                for f in shared
            ]))

    row_ind, col_ind = linear_sum_assignment(cost)

    assignments = {}
    for si, li in zip(row_ind, col_ind):
        if cost[si, li] >= _INF:
            continue
        if cost[si, li] > _REFERENCE_PROX_MAX_PX:
            continue
        assignments[labels[li]] = (seed_trajs[si], seed_ks[si])

    return assignments


def _build_red_candidates(
    stack: np.ndarray,
    nucleus_masks: list,
    *,
    k: float,
    inter_frame_max_px: float,
    minimum_points: int,
    maximum_missing_frames: int,
    p_reference_trajs_dict: dict | None = None,
    harvest_radius_px: float | None = None,
) -> tuple[list[list[tuple[int, float, float]]], list[dict]]:
    """Detect Red components, then link strictly by Red continuity.

    When ``p_reference_trajs_dict`` is supplied, P positions gate the per-frame
    detection harvest.  When it is ``None``, all eligible nuclear Red components
    are harvested and P is not read until the separate final pairing step.
    Linking always uses Red endpoints alone, gives immediately adjacent frames
    first priority, and then permits a fixed number of missing frames within the
    same ``inter_frame_max_px``.  Missing positions are never interpolated and P
    is never used as a tracking fallback.
    """
    reference_by_frame = defaultdict(list)
    if p_reference_trajs_dict is not None:
        if harvest_radius_px is None or harvest_radius_px <= 0:
            raise ValueError("P-gated Red harvest requires a positive radius")
        for label, trajectory in p_reference_trajs_dict.items():
            for frame, y, x in trajectory:
                reference_by_frame[int(frame)].append(
                    (int(label), float(y), float(x))
                )

    tracks: list[list[tuple[int, float, float]]] = []
    detection_audit: list[dict] = []
    active_indices: list[int] = []
    for frame_index, frame in enumerate(stack):
        references = reference_by_frame.get(frame_index, [])
        candidates = []
        valid = compute_valid_mask(frame)
        mean = float(frame[valid].mean())
        standard_deviation = float(frame[valid].std())
        labeled, component_count = ndimage.label(
            (frame > mean + k * standard_deviation) & valid
        )
        sizes, centroids = component_sizes_and_centroids(
            labeled, component_count, weights=frame
        )
        for component_id, (size, (y, x)) in enumerate(
            zip(sizes, centroids), start=1
        ):
            if int(size) < MIN_SPOT_PX:
                continue
            if nucleus_masks[frame_index] is not None and not point_in_mask(
                y, x, nucleus_masks[frame_index]
            ):
                continue
            if p_reference_trajs_dict is None:
                nearest_distance, nearest_label = "", ""
            else:
                distances = [
                    (float(np.hypot(y - py, x - px)), label)
                    for label, py, px in references
                ]
                if not distances:
                    continue
                nearest_distance, nearest_label = min(distances)
                if nearest_distance > harvest_radius_px:
                    continue
            candidates.append((float(y), float(x), int(component_id), int(size)))
            detection_audit.append({
                "frame": int(frame_index + 1),
                "candidate_in_frame": int(len(candidates)),
                "component_id": int(component_id),
                "area_px": int(size),
                "y_px": float(y),
                "x_px": float(x),
                "nearest_p_locus": (
                    int(nearest_label) if nearest_label != "" else ""
                ),
                "nearest_p_distance_px": (
                    float(nearest_distance) if nearest_distance != "" else ""
                ),
                "harvest_radius_px": (
                    float(harvest_radius_px)
                    if p_reference_trajs_dict is not None else ""
                ),
                "harvest_domain": (
                    "p_neighborhood"
                    if p_reference_trajs_dict is not None else "whole_nucleus"
                ),
            })

        matched_tracks: set[int] = set()
        matched_candidates: set[int] = set()
        # Cascade by temporal distance so an adjacent-frame Red continuation
        # always has priority over an older fragment.  This preserves R-only
        # identity while tolerating short segmentation/detection dropouts.
        for frame_delta in range(1, maximum_missing_frames + 2):
            previous = [
                track_index for track_index in active_indices
                if track_index not in matched_tracks
                and tracks[track_index][-1][0] == frame_index - frame_delta
            ]
            remaining_candidates = [
                candidate_index for candidate_index in range(len(candidates))
                if candidate_index not in matched_candidates
            ]
            if not previous or not remaining_candidates:
                continue
            cost = np.full((len(previous), len(candidates)), 1e9, dtype=float)
            for row, track_index in enumerate(previous):
                _last_frame, last_y, last_x = tracks[track_index][-1]
                for column in remaining_candidates:
                    y, x, _component_id, _size = candidates[column]
                    distance = float(np.hypot(y - last_y, x - last_x))
                    if distance <= inter_frame_max_px:
                        cost[row, column] = distance
            rows, columns = linear_sum_assignment(cost)
            for row, column in zip(rows, columns):
                if cost[row, column] >= 1e9:
                    continue
                track_index = previous[row]
                y, x, _component_id, _size = candidates[column]
                tracks[track_index].append((frame_index, y, x))
                matched_tracks.add(track_index)
                matched_candidates.add(int(column))

        for candidate_index, (y, x, _component_id, _size) in enumerate(candidates):
            if candidate_index in matched_candidates:
                continue
            tracks.append([(frame_index, y, x)])
            matched_tracks.add(len(tracks) - 1)
        active_indices = sorted(
            {
                track_index for track_index in active_indices
                if frame_index - tracks[track_index][-1][0] <= maximum_missing_frames
            }
            | matched_tracks
        )

    retained_with_source = [
        (source_index, track)
        for source_index, track in enumerate(tracks)
        if len(track) >= minimum_points
    ]
    retained_with_source.sort(
        key=lambda item: (-len(item[1]), item[1][0][0], item[1][0][2], item[1][0][1])
    )
    retained_id = {
        source_index: candidate_index
        for candidate_index, (source_index, _track) in enumerate(
            retained_with_source, start=1
        )
    }
    detection_to_track = {}
    for source_index, track in enumerate(tracks):
        for frame, y, x in track:
            detection_to_track[(int(frame + 1), round(y, 6), round(x, 6))] = source_index
    for row in detection_audit:
        source_index = detection_to_track.get(
            (row["frame"], round(row["y_px"], 6), round(row["x_px"], 6))
        )
        row["red_candidate"] = retained_id.get(source_index, "")
        row["retained_minimum_points"] = source_index in retained_id
    retained = [track for _source_index, track in retained_with_source]
    return retained, detection_audit


def build_p_gated_red_candidates(
    stack: np.ndarray,
    reference_trajs_dict: dict,
    nucleus_masks: list,
    *,
    k: float,
    harvest_radius_px: float,
    inter_frame_max_px: float,
    minimum_points: int,
    maximum_missing_frames: int,
) -> tuple[list[list[tuple[int, float, float]]], list[dict]]:
    """Harvest Red near P in every frame, then link by Red continuity."""
    return _build_red_candidates(
        stack,
        nucleus_masks,
        k=k,
        inter_frame_max_px=inter_frame_max_px,
        minimum_points=minimum_points,
        maximum_missing_frames=maximum_missing_frames,
        p_reference_trajs_dict=reference_trajs_dict,
        harvest_radius_px=harvest_radius_px,
    )


def build_autonomous_red_candidates(
    stack: np.ndarray,
    nucleus_masks: list,
    *,
    k: float,
    inter_frame_max_px: float,
    minimum_points: int,
    maximum_missing_frames: int,
) -> tuple[list[list[tuple[int, float, float]]], list[dict]]:
    """Build Red tracks across the nucleus without consulting P positions."""
    return _build_red_candidates(
        stack,
        nucleus_masks,
        k=k,
        inter_frame_max_px=inter_frame_max_px,
        minimum_points=minimum_points,
        maximum_missing_frames=maximum_missing_frames,
    )


def pair_red_candidates_to_purple(
    red_candidates: list[list[tuple[int, float, float]]],
    reference_trajs_dict: dict,
    *,
    maximum_median_distance_px: float,
    minimum_shared_frames: int,
    movie_frame_count: int,
    minimum_movie_coverage_fraction: float,
    uniqueness_margin_px: float,
) -> tuple[dict, list[dict], list[dict]]:
    """Pair independent Red tracks by common-frame median P-R distance."""
    effective_minimum_shared_frames = max(
        minimum_shared_frames,
        int(np.ceil(movie_frame_count * minimum_movie_coverage_fraction)),
    )
    labels = sorted(reference_trajs_dict)
    p_by_label = {
        label: {int(frame): (float(y), float(x)) for frame, y, x in trajectory}
        for label, trajectory in reference_trajs_dict.items()
    }
    n_red, n_p = len(red_candidates), len(labels)
    median = np.full((n_red, n_p), np.inf, dtype=float)
    shared_count = np.zeros((n_red, n_p), dtype=int)
    p95 = np.full((n_red, n_p), np.nan, dtype=float)
    per_frame_rows: list[dict] = []
    for red_index, trajectory in enumerate(red_candidates):
        r_by_frame = {
            int(frame): (float(y), float(x)) for frame, y, x in trajectory
        }
        for p_index, label in enumerate(labels):
            shared = sorted(set(r_by_frame) & set(p_by_label[label]))
            distances = []
            for frame in shared:
                ry, rx = r_by_frame[frame]
                py, px = p_by_label[label][frame]
                distance = float(np.hypot(ry - py, rx - px))
                distances.append(distance)
                per_frame_rows.append({
                    "frame": int(frame + 1),
                    "p_locus": int(label),
                    "r_candidate": int(red_index + 1),
                    "p_x_px": px,
                    "p_y_px": py,
                    "r_x_px": rx,
                    "r_y_px": ry,
                    "distance_px": distance,
                })
            shared_count[red_index, p_index] = len(shared)
            if len(shared) >= minimum_shared_frames:
                median[red_index, p_index] = float(np.median(distances))
                p95[red_index, p_index] = float(np.percentile(distances, 95))

    valid_cost = np.where(
        (shared_count >= effective_minimum_shared_frames)
        & (median <= maximum_median_distance_px),
        median,
        1e9,
    )
    assignments = {}
    pair_rows: list[dict] = []
    if n_red and n_p:
        rows, columns = linear_sum_assignment(valid_cost)
        for red_index, p_index in zip(rows, columns):
            label = labels[p_index]
            distance = float(valid_cost[red_index, p_index])
            competing_r = np.delete(valid_cost[:, p_index], red_index)
            competing_p = np.delete(valid_cost[red_index, :], p_index)
            next_r = float(np.min(competing_r)) if competing_r.size else np.inf
            next_p = float(np.min(competing_p)) if competing_p.size else np.inf
            r_margin = next_r - distance
            p_margin = next_p - distance
            reciprocal_best = (
                distance < 1e9
                and red_index == int(np.argmin(valid_cost[:, p_index]))
                and p_index == int(np.argmin(valid_cost[red_index, :]))
            )
            unique = (
                reciprocal_best
                and r_margin >= uniqueness_margin_px
                and p_margin >= uniqueness_margin_px
            )
            if unique:
                assignments[int(label)] = red_candidates[red_index]
            pair_rows.append({
                "p_locus": int(label),
                "r_candidate": int(red_index + 1),
                "r_points": int(len(red_candidates[red_index])),
                "movie_frames": int(movie_frame_count),
                "movie_coverage_fraction": float(
                    len(red_candidates[red_index]) / movie_frame_count
                ),
                "common_frames": int(shared_count[red_index, p_index]),
                "minimum_required_common_frames": int(
                    effective_minimum_shared_frames
                ),
                "median_distance_px": (
                    float(median[red_index, p_index])
                    if np.isfinite(median[red_index, p_index]) else ""
                ),
                "p95_distance_px": (
                    float(p95[red_index, p_index])
                    if np.isfinite(p95[red_index, p_index]) else ""
                ),
                "next_r_margin_px": r_margin if np.isfinite(r_margin) else "inf",
                "next_p_margin_px": p_margin if np.isfinite(p_margin) else "inf",
                "reciprocal_best": bool(reciprocal_best),
                "decision": "ACCEPT_UNIQUE" if unique else "REJECT_AMBIGUOUS_OR_OUTSIDE",
            })
    return assignments, pair_rows, per_frame_rows


def propagate_from_seed(stack: np.ndarray, roi: tuple, seed_traj: list,
                         reference_indexed_pos: list, reference_centroid_avg: tuple,
                         k: float, inter_frame_max_px: float = None) -> list:
    """
    Propagate tracking from a pre-computed seed trajectory within roi.

    Starts from the last frame in seed_traj and continues to the end of the
    stack.  k is the detection threshold (may differ from channel base k when
    the seed came from adaptive blob splitting).

    Primary linking: candidate within inter_frame_max_px of last position AND
    within _REFERENCE_PROX_MAX_PX of the reference spot.

    Fallback (same as track_channel_in_roi): when primary yields nothing,
    accept the candidate closest to the reference spot within _REFERENCE_PROX_MAX_PX.
    This recovers highly mobile loci whose frame-to-frame displacement exceeds
    inter_frame_max_px but whose signal stays near the reference anchor.

    Returns the complete trajectory: seed_traj positions + propagated positions.
    """
    if inter_frame_max_px is None:
        inter_frame_max_px = _INTER_FRAME_MAX_PX
    if not seed_traj:
        return []

    top, left, bottom, right = roi
    n_frames = stack.shape[0]
    reference_tracked = {t: (fy, fx) for t, fy, fx in reference_indexed_pos}

    def candidates_in_roi(frame_arr):
        valid  = compute_valid_mask(frame_arr)
        m, s   = frame_arr[valid].mean(), frame_arr[valid].std()
        labeled, n = ndimage.label((frame_arr > (m + k * s)) & valid)
        found = []
        sizes, centroids = component_sizes_and_centroids(labeled, n)
        for size, (cy, cx) in zip(sizes, centroids):
            if int(size) < MIN_SPOT_PX:
                continue
            if top <= cy < bottom and left <= cx < right:
                found.append((cy, cx))
        return found

    positions  = list(seed_traj)
    seed_frame = seed_traj[-1][0]
    last_pos   = (seed_traj[-1][1], seed_traj[-1][2])

    for f in range(seed_frame + 1, n_frames):
        cands = candidates_in_roi(stack[f])
        ref_y, ref_x = reference_tracked.get(f, reference_centroid_avg)

        # Primary: inter-frame constraint + reference proximity
        cands_primary = [(cy, cx) for cy, cx in cands
                          if np.hypot(cy - last_pos[0], cx - last_pos[1]) <= inter_frame_max_px
                          and np.hypot(cy - ref_y, cx - ref_x) <= _REFERENCE_PROX_MAX_PX]
        if cands_primary:
            best = min(cands_primary,
                       key=lambda p: np.hypot(p[0] - last_pos[0], p[1] - last_pos[1]))
            last_pos = best
            positions.append((f, best[0], best[1]))
            continue

        # Fallback: reference proximity only (handles highly mobile loci)
        cands_fallback = [(cy, cx) for cy, cx in cands
                          if np.hypot(cy - ref_y, cx - ref_x) <= _REFERENCE_PROX_MAX_PX]
        if cands_fallback:
            best = min(cands_fallback, key=lambda p: np.hypot(p[0] - ref_y, p[1] - ref_x))
            last_pos = best
            positions.append((f, best[0], best[1]))

    return positions


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build reference and target trajectories from registered channel TIFFs."
    )
    parser.add_argument("nucleus_path", type=Path, help="Path to the *_Nucleus.tif file.")
    parser.add_argument(
        "--reference-channel",
        choices=CHANNELS,
        default="purple",
        help=(
            "Legacy standalone Stage-1 anchor (default: purple). Production v4.1 "
            "always supplies the locked anchor from its experiment profile."
        ),
    )
    parser.add_argument(
        "--nucleus-mask",
        type=Path,
        help=(
            "Optional drift-aligned binary micro-SAM TYX mask. When supplied, "
            "it is used directly for anchor filtering instead of rebuilding a "
            "nucleus boundary with per-frame intensity Otsu."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for Stage-1 CSV/ROI/mask outputs (default: TIFF directory).",
    )
    parser.add_argument(
        "--reference-seed-k",
        type=float,
        help="Override the time-average reference candidate threshold coefficient.",
    )
    parser.add_argument(
        "--reference-tracking-k",
        type=float,
        help="Override the independent per-frame reference tracking coefficient.",
    )
    parser.add_argument(
        "--reference-edge-width-px",
        type=float,
        default=REFERENCE_EDGE_WIDTH_PX,
        help="Inner nucleus boundary-band width used for reference candidate filtering.",
    )
    parser.add_argument(
        "--reference-max-edge-fraction",
        type=float,
        default=REFERENCE_MAX_EDGE_FRACTION,
        help="Maximum fraction of an intact reference component inside the boundary band.",
    )
    parser.add_argument(
        "--target-reference-mode",
        choices=("legacy", "p_gated_r_autonomous", "independent_r_autonomous"),
        default="legacy",
        help=(
            "legacy keeps historical target tracking; p_gated_r_autonomous "
            "uses P for every-frame Red harvest; independent_r_autonomous "
            "builds Red tracks over the whole nucleus and consults P only at final pairing."
        ),
    )
    parser.add_argument(
        "--red-harvest-radius-um", type=float, default=DSB_RED_HARVEST_RADIUS_UM
    )
    parser.add_argument(
        "--red-min-track-points", type=int, default=DSB_RED_MIN_TRACK_POINTS
    )
    parser.add_argument(
        "--red-min-shared-frames", type=int, default=DSB_RED_MIN_SHARED_FRAMES
    )
    parser.add_argument(
        "--red-min-movie-coverage-fraction",
        type=float,
        default=DSB_RED_MIN_MOVIE_COVERAGE_FRACTION,
    )
    parser.add_argument(
        "--red-max-missing-frames", type=int, default=DSB_RED_MAX_MISSING_FRAMES
    )
    parser.add_argument(
        "--red-uniqueness-margin-px",
        type=float,
        default=DSB_RED_UNIQUENESS_MARGIN_PX,
    )
    args = parser.parse_args()

    nucleus_path = args.nucleus_path.resolve()
    reference_channel = args.reference_channel
    reference_seed_k = (
        args.reference_seed_k
        if args.reference_seed_k is not None
        else REFERENCE_SEED_K[reference_channel]
    )
    reference_tracking_k = (
        args.reference_tracking_k
        if args.reference_tracking_k is not None
        else REFERENCE_TRACKING_K[reference_channel]
    )
    if reference_seed_k <= 0 or reference_tracking_k <= 0:
        parser.error("reference k values must be positive")
    if args.reference_edge_width_px < 0:
        parser.error("--reference-edge-width-px must be non-negative")
    if not 0 <= args.reference_max_edge_fraction <= 1:
        parser.error("--reference-max-edge-fraction must be in [0, 1]")
    if (
        args.target_reference_mode in {
            "p_gated_r_autonomous", "independent_r_autonomous"
        }
        and reference_channel != "purple"
    ):
        parser.error(
            f"{args.target_reference_mode} requires --reference-channel purple"
        )
    if args.red_harvest_radius_um <= 0:
        parser.error("--red-harvest-radius-um must be positive")
    if args.red_min_track_points < 1 or args.red_min_shared_frames < 1:
        parser.error("red minimum point/shared-frame counts must be positive")
    if not 0 < args.red_min_movie_coverage_fraction <= 1:
        parser.error("--red-min-movie-coverage-fraction must be in (0, 1]")
    if args.red_max_missing_frames < 0:
        parser.error("--red-max-missing-frames must be non-negative")
    if args.red_uniqueness_margin_px < 0:
        parser.error("--red-uniqueness-margin-px must be non-negative")
    target_channels = tuple(channel for channel in CHANNELS if channel != reference_channel)
    reference_prefix = CHANNEL_PREFIX[reference_channel]
    if not nucleus_path.name.endswith('_Nucleus.tif'):
        print("ERROR: input filename must end with '_Nucleus.tif'")
        sys.exit(1)

    stem = str(nucleus_path)[:-len('_Nucleus.tif')]
    paths = {
        'nucleus': nucleus_path,
        'green':   Path(stem + '_green.tif'),
        'red':     Path(stem + '_red.tif'),
        'purple':  Path(stem + '_purple.tif'),
    }
    for ch, p in paths.items():
        if not p.exists():
            print(f"ERROR: {ch} file not found: {p}")
            sys.exit(1)

    out_dir = args.output_dir.resolve() if args.output_dir else nucleus_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Input   : {nucleus_path.name}")
    print(f"Reference channel: {reference_channel} ({paths[reference_channel].name})")
    print(f"Target channels  : {', '.join(target_channels)}")
    print(f"Red     : {paths['red'].name}")
    print(f"Purple  : {paths['purple'].name}")
    print(f"Output  : {out_dir}")

    # ── Derive pixel size from .tif metadata ─────────────────────────────────
    global PIXEL_SIZE_UM, _INTER_FRAME_MAX_PX, _INTER_FRAME_MAX_PX_RED, _REFERENCE_PROX_MAX_PX
    try:
        PIXEL_SIZE_UM = read_pixel_size_from_tif(nucleus_path)
    except ValueError as e:
        print(f"ERROR reading pixel size from metadata: {e}")
        sys.exit(1)
    _INTER_FRAME_MAX_PX     = INTER_FRAME_MAX_NM     * PIXEL_SIZE_UM / 1000.0
    _INTER_FRAME_MAX_PX_RED = INTER_FRAME_MAX_NM_RED * PIXEL_SIZE_UM / 1000.0
    _REFERENCE_PROX_MAX_PX  = REFERENCE_PROX_MAX_UM  * PIXEL_SIZE_UM

    print(f"Pixel   : {PIXEL_SIZE_UM:.4f} px/µm (from metadata)  "
          f"inter-frame limit purple={INTER_FRAME_MAX_NM} nm ({_INTER_FRAME_MAX_PX:.1f} px)  "
          f"red={INTER_FRAME_MAX_NM_RED} nm ({_INTER_FRAME_MAX_PX_RED:.1f} px)  "
          f"reference-proximity limit {REFERENCE_PROX_MAX_UM} µm ({_REFERENCE_PROX_MAX_PX:.1f} px)  "
          f"padding {PADDING} px")
    print(f"Blob    : MAX_BLOB_PX={MAX_BLOB_PX} px  "
          f"adaptive k steps={_ADAPTIVE_K_STEPS} (overlap groups only)")

    # ── Load stacks ───────────────────────────────────────────────────────────
    print("\nLoading stacks...")
    stacks   = {ch: load_stack(p) for ch, p in paths.items()}
    H, W     = stacks[reference_channel].shape[1], stacks[reference_channel].shape[2]
    n_frames = stacks[reference_channel].shape[0]
    avgs     = {ch: stacks[ch].mean(axis=0) for ch in CHANNELS}
    print(f"  {n_frames} frames, {H}×{W} px")

    # ── Per-frame nucleus masks ───────────────────────────────────────────────
    if args.nucleus_mask:
        supplied_path = args.nucleus_mask.resolve()
        if not supplied_path.is_file():
            print(f"ERROR: supplied nucleus mask not found: {supplied_path}")
            sys.exit(1)
        supplied = load_stack(supplied_path) > 0
        expected_shape = (n_frames, H, W)
        if supplied.shape != expected_shape:
            print(
                f"ERROR: supplied nucleus mask shape {supplied.shape} does not "
                f"match channel stacks {expected_shape}: {supplied_path}"
            )
            sys.exit(1)
        empty_frames = np.flatnonzero(~supplied.any(axis=(1, 2)))
        if len(empty_frames):
            preview = ", ".join(str(int(index + 1)) for index in empty_frames[:10])
            print(f"ERROR: supplied nucleus mask is empty in frame(s): {preview}")
            sys.exit(1)
        print(f"\nUsing supplied drift-aligned micro-SAM nucleus mask: {supplied_path}")
        nucleus_masks = [supplied[index] for index in range(n_frames)]
    else:
        print(f"\nBuilding per-frame nucleus masks (Otsu + Gaussian σ={NUCLEUS_SIGMA}, "
              f"FILL_RATIO={FILL_RATIO})...")
        nucleus_masks = detect_nucleus_frames(stacks['nucleus'])
    n_detected = sum(1 for m in nucleus_masks if m is not None)
    print(f"  Nucleus detected in {n_detected}/{n_frames} frames")
    masks_path = out_dir / 'Nucleus_masks.tif'
    save_nucleus_masks_tiff(nucleus_masks, H, W, masks_path)
    print(f"  Saved : {masks_path.name}")
    available_nucleus_masks = np.stack(
        [mask for mask in nucleus_masks if mask is not None]
    ).astype(bool)
    reference_consensus_mask = (
        available_nucleus_masks.mean(axis=0)
        >= REFERENCE_MASK_OCCUPANCY_FRACTION
    )

    # ── Signal detection on green averaged image ──────────────────────────────
    print(f"\nDetecting {reference_channel} reference signal clusters (time-averaged image)...")
    _valid = compute_valid_mask(avgs[reference_channel])
    ref_mean = float(avgs[reference_channel][_valid].mean())
    ref_std = float(avgs[reference_channel][_valid].std())
    reference_clusters, reference_detection_audit = detect_signal_clusters(
        avgs[reference_channel],
        reference_seed_k,
        MIN_SPOT_PX,
        N_MAX,
        reference_consensus_mask,
        args.reference_edge_width_px,
        args.reference_max_edge_fraction,
    )
    print(f"  {reference_channel:<7}: {len(reference_clusters)} cluster(s)  "
          f"threshold = {ref_mean:.1f} + {reference_seed_k}×{ref_std:.1f} = "
          f"{ref_mean + reference_seed_k*ref_std:.1f}  "
          f"sizes = {[c['size'] for c in reference_clusters]}")
    reference_detection_audit.update({
        'reference_channel': reference_channel,
        'reference_tracking_k': float(reference_tracking_k),
        'coordinate_contract': coordinate_system.contract_manifest(),
        'mask_occupancy_fraction': REFERENCE_MASK_OCCUPANCY_FRACTION,
        'selection_order': [
            'global connected components on the valid time-average image',
            'minimum component area',
            '100 percent intact-component containment in consensus nucleus mask',
            'inner boundary-band fraction filter',
            'descending original component mean intensity',
            'top-N cap',
        ],
    })
    (out_dir / 'reference_detection_audit.json').write_text(
        json.dumps(reference_detection_audit, indent=2), encoding='utf-8'
    )

    if not reference_clusters:
        print(f"\nNo {reference_channel} reference signal clusters found. "
              f"Try lowering reference_seed_k or MIN_SPOT_PX.")
        sys.exit(0)

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  PASS 1 — Green tracking and ROI computation                        ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    print("\n" + "═"*60)
    print(f"Pass 1 — {reference_channel.capitalize()} reference tracking and ROI computation")
    print("═"*60)

    accepted    = []
    accepted_rois = []
    reference_tracking_audit = []

    for idx, spot in enumerate(reference_clusters):
        cy, cx = spot['centroid']
        print(f"\n  Spot {idx+1}: centroid=({cy:.1f}, {cx:.1f})  "
              f"size={spot['size']} px  intensity={spot['intensity']:.1f}")

        indexed_pos = track_spot_indexed(
            stacks[reference_channel], (cy, cx), reference_tracking_k
        )
        print(f"    {reference_channel.capitalize()} tracked in {len(indexed_pos)}/{n_frames} frames")
        if not indexed_pos:
            print(f"    ✗ Skipped: reference spot not trackable")
            reference_tracking_audit.append({
                'seed_rank': idx + 1,
                'decision': 'REJECT_NOT_TRACKABLE',
                'trajectory_points': 0,
            })
            continue

        checkable = [(t, fy, fx) for t, fy, fx in indexed_pos
                     if nucleus_masks[t] is not None]
        outside   = [(t, fy, fx) for t, fy, fx in checkable
                     if not point_in_mask(fy, fx, nucleus_masks[t])]
        frac_outside = len(outside) / len(checkable) if checkable else 0.0
        if frac_outside > NUCLEUS_OUTSIDE_FRAC:
            print(f"    ✗ Skipped: {len(outside)}/{len(checkable)} checkable frames "
                  f"({100*frac_outside:.1f}%) outside nucleus mask "
                  f"(limit {100*NUCLEUS_OUTSIDE_FRAC:.0f}%)")
            reference_tracking_audit.append({
                'seed_rank': idx + 1,
                'decision': 'REJECT_TRACK_OUTSIDE_NUCLEUS',
                'trajectory_points': len(indexed_pos),
                'checkable_points': len(checkable),
                'outside_points': len(outside),
                'outside_fraction': frac_outside,
            })
            continue
        if outside:
            print(f"    ~ {len(outside)}/{len(checkable)} frame(s) outside nucleus "
                  f"({100*frac_outside:.1f}%) — within tolerance, accepted")
        else:
            print(f"    ✓ All reference positions within nucleus")

        ys = [p[1] for p in indexed_pos]
        xs = [p[2] for p in indexed_pos]
        print(f"    Motion: Δy={max(ys)-min(ys):.1f} px  Δx={max(xs)-min(xs):.1f} px")

        t_roi, l, b, r = compute_roi_from_trajectory(indexed_pos, H, W)
        print(f"    ROI: top={t_roi} left={l} bottom={b} right={r}  "
              f"({r-l}×{b-t_roi} px)")

        label = idx + 1
        accepted.append((label, indexed_pos, (t_roi, l, b, r), (cy, cx)))
        accepted_rois.append(roi_dict(t_roi, l, b, r, label))
        reference_tracking_audit.append({
            'seed_rank': idx + 1,
            'output_locus': label,
            'decision': 'ACCEPT',
            'trajectory_points': len(indexed_pos),
            'frame_start_1based': int(indexed_pos[0][0] + 1),
            'frame_end_1based': int(indexed_pos[-1][0] + 1),
            'checkable_points': len(checkable),
            'outside_points': len(outside),
            'outside_fraction': frac_outside,
        })

        reference_csv = out_dir / f'{reference_prefix}_loci{label}_traj_rela2wholeimg.csv'
        save_trajectory_csv(indexed_pos, reference_csv)
        print(f"    Saved: {reference_csv.name}  ({len(indexed_pos)} points)")

        if len(accepted) >= N_MAX:
            break

    if not accepted:
        reference_detection_audit['reference_tracking'] = reference_tracking_audit
        (out_dir / 'reference_detection_audit.json').write_text(
            json.dumps(reference_detection_audit, indent=2), encoding='utf-8'
        )
        print(f"\nNo {reference_channel} reference loci accepted. Exiting.")
        sys.exit(0)

    reference_detection_audit['reference_tracking'] = reference_tracking_audit
    reference_detection_audit['accepted_reference_count'] = len(accepted)

    if args.target_reference_mode in {
        "p_gated_r_autonomous", "independent_r_autonomous"
    }:
        reference_trajs_dict = {item[0]: item[1] for item in accepted}
        harvest_radius_px = args.red_harvest_radius_um * PIXEL_SIZE_UM
        if args.target_reference_mode == "p_gated_r_autonomous":
            red_candidates, red_detection_rows = build_p_gated_red_candidates(
                stacks["red"],
                reference_trajs_dict,
                nucleus_masks,
                k=TARGET_TRACKING_K["red"],
                harvest_radius_px=harvest_radius_px,
                inter_frame_max_px=_INTER_FRAME_MAX_PX_RED,
                minimum_points=args.red_min_track_points,
                maximum_missing_frames=args.red_max_missing_frames,
            )
            red_harvest_domain = "per-frame 2.5 um P neighborhood"
        else:
            red_candidates, red_detection_rows = build_autonomous_red_candidates(
                stacks["red"],
                nucleus_masks,
                k=TARGET_TRACKING_K["red"],
                inter_frame_max_px=_INTER_FRAME_MAX_PX_RED,
                minimum_points=args.red_min_track_points,
                maximum_missing_frames=args.red_max_missing_frames,
            )
            red_harvest_domain = "whole per-frame nucleus; no P coordinates read"
        red_assignments, red_pair_rows, red_pair_frame_rows = pair_red_candidates_to_purple(
            red_candidates,
            reference_trajs_dict,
            maximum_median_distance_px=harvest_radius_px,
            minimum_shared_frames=args.red_min_shared_frames,
            movie_frame_count=int(stacks["red"].shape[0]),
            minimum_movie_coverage_fraction=(
                args.red_min_movie_coverage_fraction
            ),
            uniqueness_margin_px=args.red_uniqueness_margin_px,
        )
        for candidate_index, trajectory in enumerate(red_candidates, start=1):
            save_trajectory_csv(
                trajectory,
                out_dir / f"R_candidate{candidate_index:03d}_traj_rela2wholeimg.csv",
            )
        for label, trajectory in sorted(red_assignments.items()):
            save_trajectory_csv(
                trajectory,
                out_dir / f"R_loci{label}_traj_rela2wholeimg.csv",
            )
        for filename, rows in (
            ("red_harvest_detections.csv", red_detection_rows),
            ("red_pair_summary.csv", red_pair_rows),
            ("red_pair_common_frames.csv", red_pair_frame_rows),
        ):
            path = out_dir / filename
            if rows:
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
            else:
                path.write_text("", encoding="utf-8")
        reference_detection_audit["red_reference_mode"] = {
            "mode": args.target_reference_mode,
            "harvest_domain": red_harvest_domain,
            "harvest_radius_um": (
                float(args.red_harvest_radius_um)
                if args.target_reference_mode == "p_gated_r_autonomous" else None
            ),
            "final_pair_maximum_median_distance_um": float(
                args.red_harvest_radius_um
            ),
            "inter_frame_max_nm": float(INTER_FRAME_MAX_NM_RED),
            "continuity": (
                "red-to-red endpoints only; adjacent frames prioritized; fixed-radius "
                "short-gap continuation; no interpolation; no P fallback"
            ),
            "maximum_missing_frames": int(args.red_max_missing_frames),
            "minimum_track_points": int(args.red_min_track_points),
            "pair_metric": "median P-R distance on common frames",
            "minimum_shared_frames": int(args.red_min_shared_frames),
            "minimum_movie_coverage_fraction": float(
                args.red_min_movie_coverage_fraction
            ),
            "effective_minimum_shared_frames": int(max(
                args.red_min_shared_frames,
                np.ceil(
                    stacks["red"].shape[0]
                    * args.red_min_movie_coverage_fraction
                ),
            )),
            "uniqueness_margin_px": float(args.red_uniqueness_margin_px),
            "red_candidate_count": len(red_candidates),
            "accepted_pair_count": len(red_assignments),
            "accepted_p_loci": sorted(red_assignments),
        }
        target_channels = tuple(channel for channel in target_channels if channel != "red")
        print(
            f"\n{args.target_reference_mode} Red: "
            f"{len(red_candidates)} retained candidate(s), "
            f"{len(red_assignments)} unique P-R pair(s); Red removed from legacy target pass"
        )
    (out_dir / 'reference_detection_audit.json').write_text(
        json.dumps(reference_detection_audit, indent=2), encoding='utf-8'
    )

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  Overlap detection                                                  ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    print(f"\n{'═'*60}")
    print("Overlap detection")
    print(f"{'═'*60}")

    overlap_groups = find_overlap_groups(accepted)

    for group_indices in overlap_groups:
        labels = [accepted[i][0] for i in group_indices]
        if len(group_indices) > 1:
            print(f"  ⚠ Overlapping group detected: loci {labels} — will use joint seeding")
        else:
            print(f"  Singleton: loci{labels[0]} (no ROI overlap)")

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  PASS 2 — Purple and Red tracking                                   ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    print(f"\n{'═'*60}")
    print(f"Pass 2 — target-channel tracking ({', '.join(target_channels)})")
    print(f"{'═'*60}")

    for group_indices in overlap_groups:
        group = [accepted[i] for i in group_indices]

        if len(group) == 1:
            # ── No overlap: identical to v2.8 / v2.10 ────────────────────────
            label, reference_traj, roi, centroid_avg = group[0]
            print(f"\n  Loci {label} (singleton — standard tracking):")

            for ch in target_channels:
                prefix = CHANNEL_PREFIX[ch]
                ifpx = _INTER_FRAME_MAX_PX_RED if ch == 'red' else _INTER_FRAME_MAX_PX
                print(f"    ── {ch.capitalize()} tracking ──")
                pos = track_channel_in_roi(
                    stacks[ch], roi, reference_traj, centroid_avg, TARGET_TRACKING_K[ch],
                    inter_frame_max_px=ifpx)
                if pos:
                    csv_path = out_dir / f'{prefix}_loci{label}_traj_rela2wholeimg.csv'
                    save_trajectory_csv(pos, csv_path)
                    print(f"    Saved: {csv_path.name}  ({len(pos)} points)")
                else:
                    print(f"    {ch.capitalize()}: no trajectory found within ROI "
                          f"(seed not found in first {SEED_MAX_FRAME} frames)")

        else:
            # ── Overlapping group: joint seeding with adaptive k ──────────────
            loci_labels = [acc[0] for acc in group]
            print(f"\n  Overlap group: loci {loci_labels} — joint seeding")

            group_rois = [acc[2] for acc in group]
            union_mask = compute_union_mask(group_rois, H, W)

            for ch in target_channels:
                prefix = CHANNEL_PREFIX[ch]
                ifpx = _INTER_FRAME_MAX_PX_RED if ch == 'red' else _INTER_FRAME_MAX_PX
                print(f"    ── {ch.capitalize()} tracking (joint) ──")

                seed_trajs, seed_ks = find_seed_trajectories_in_mask(
                    stacks[ch], union_mask, SEED_MAX_FRAME, TARGET_TRACKING_K[ch],
                    inter_frame_max_px=ifpx)
                print(f"    Seed trajectories found in union ROI: {len(seed_trajs)}")

                reference_trajs_dict = {acc[0]: acc[1] for acc in group}
                assignments = match_seeds_to_reference(
                    seed_trajs, seed_ks, reference_trajs_dict)

                for label, reference_traj, roi, centroid_avg in group:
                    if label in assignments:
                        seed_traj, k_propagate = assignments[label]
                        _sbf = {f: (y, x) for f, y, x in seed_traj}
                        _reference_by_frame = {f: (y, x) for f, y, x in reference_traj}
                        _shared = [f for f in _sbf if f in _reference_by_frame]
                        avg_d = float(np.mean([
                            np.hypot(_sbf[f][0] - _reference_by_frame[f][0],
                                     _sbf[f][1] - _reference_by_frame[f][1])
                            for f in _shared
                        ])) if _shared else float('nan')
                        print(f"    Loci{label}: matched seed "
                              f"(seed frames {[s[0] for s in seed_traj]}, "
                              f"avg dist to {reference_channel} reference = {avg_d:.2f} px, "
                              f"propagation k={k_propagate})")
                        pos = propagate_from_seed(
                            stacks[ch], roi, seed_traj,
                            reference_traj, centroid_avg, k_propagate,
                            inter_frame_max_px=ifpx)
                        if pos:
                            csv_path = out_dir / (
                                f'{prefix}_loci{label}_traj_rela2wholeimg.csv')
                            save_trajectory_csv(pos, csv_path)
                            print(f"    Saved: {csv_path.name}  ({len(pos)} points)")
                        else:
                            print(f"    Loci{label} {ch}: seed matched but propagation "
                                  f"yielded 0 points within individual ROI")
                    else:
                        print(f"    Loci{label} {ch}: no unique seed match found "
                              f"(seed candidates={len(seed_trajs)}, "
                              f"competing loci={len(group)}) — no trajectory written")

    # ── Save ROI zip ──────────────────────────────────────────────────────────
    reference_zip = out_dir / f'RoiSet_{reference_channel}.zip'
    save_roi_zip(accepted_rois, reference_zip, out_dir)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print("Summary")
    print(f"{'═'*60}")
    print(f"  {reference_channel.capitalize()} reference ROIs ({len(accepted_rois)}): "
          f"{['loci'+str(r['label']) for r in accepted_rois]}")
    n_overlap = sum(1 for g in overlap_groups if len(g) > 1)
    if n_overlap:
        print(f"  Overlap groups: {n_overlap} (joint seeding + adaptive k applied)")
    print(f"\n  Nucleus masks → {masks_path.name}")
    print("\nDone.")


if __name__ == '__main__':
    main()
