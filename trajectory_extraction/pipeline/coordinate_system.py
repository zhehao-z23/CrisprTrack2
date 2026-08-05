#!/usr/bin/env python3
"""Canonical coordinate conversions shared by trajectory and feature workflows.

Image arrays and Matplotlib ``imshow`` use zero-based pixel-centre coordinates:
the centre of the top-left pixel is (x=0, y=0).  Automatic MATLAB/Python CSVs
encode that same centre as one-based pixel-centre nanometres.  ThunderSTORM
ROI-local CSVs encode the top-left pixel centre at 0.5 px, while Fiji ROI
``left``/``top`` values are zero-based pixel-edge offsets.
"""

from __future__ import annotations

import numpy as np


CONVENTION_VERSION = "oligolivefish-pixel-centre-v1"
AUTOMATIC_CSV_CONVENTION = "whole-image 1-based pixel centres in nm"
THUNDERSTORM_CSV_CONVENTION = "ROI-local 0.5-based pixel centres in nm"
IMAGE_ARRAY_CONVENTION = "zero-based pixel centres; x=column, y=row, origin=upper"
FRAME_CONVENTION = "trajectory CSV frame is 1-based; array index is frame-1"


def _pixel_size(pixel_size_nm: float) -> float:
    value = float(pixel_size_nm)
    if not np.isfinite(value) or value <= 0:
        raise ValueError("pixel_size_nm must be positive and finite")
    return value


def automatic_nm_to_image_px(values_nm, pixel_size_nm: float):
    """Convert whole-image automatic CSV positions to zero-based pixel centres."""
    return np.asarray(values_nm, dtype=float) / _pixel_size(pixel_size_nm) - 1.0


def image_px_to_automatic_nm(values_px, pixel_size_nm: float):
    """Encode zero-based image pixel centres in the automatic CSV convention."""
    return (np.asarray(values_px, dtype=float) + 1.0) * _pixel_size(pixel_size_nm)


def matlab_one_based_px_to_automatic_nm(values_px, pixel_size_nm: float):
    """Encode MATLAB one-based pixel-centre coordinates as automatic CSV nm."""
    return np.asarray(values_px, dtype=float) * _pixel_size(pixel_size_nm)


def thunderstorm_roi_nm_to_image_px(
    values_nm,
    pixel_size_nm: float,
    roi_edge_offset_px: float,
):
    """Convert ThunderSTORM ROI-local centres plus a Fiji ROI edge offset."""
    return (
        np.asarray(values_nm, dtype=float) / _pixel_size(pixel_size_nm)
        - 0.5
        + float(roi_edge_offset_px)
    )


def csv_frame_to_array_index(frame):
    """Convert one-based trajectory frame numbers to zero-based array indices."""
    values = np.asarray(frame)
    indices = values.astype(int) - 1
    if np.any(indices < 0) or np.any(values != values.astype(int)):
        raise ValueError("trajectory frames must be positive integers")
    return indices


def automatic_nm_to_image_xy(x_nm, y_nm, pixel_size_nm: float):
    return (
        automatic_nm_to_image_px(x_nm, pixel_size_nm),
        automatic_nm_to_image_px(y_nm, pixel_size_nm),
    )


def thunderstorm_roi_nm_to_image_xy(
    x_nm,
    y_nm,
    pixel_size_nm: float,
    roi_left_edge_px: float,
    roi_top_edge_px: float,
):
    return (
        thunderstorm_roi_nm_to_image_px(x_nm, pixel_size_nm, roi_left_edge_px),
        thunderstorm_roi_nm_to_image_px(y_nm, pixel_size_nm, roi_top_edge_px),
    )


def contract_manifest() -> dict:
    return {
        "version": CONVENTION_VERSION,
        "image_arrays": IMAGE_ARRAY_CONVENTION,
        "automatic_csv": AUTOMATIC_CSV_CONVENTION,
        "thunderstorm_csv": THUNDERSTORM_CSV_CONVENTION,
        "frames": FRAME_CONVENTION,
        "automatic_overlay_formula": "image_px = automatic_nm / pixel_size_nm - 1",
        "automatic_export_formula": "automatic_nm = (image_px + 1) * pixel_size_nm",
        "thunderstorm_overlay_formula": (
            "image_px = roi_edge_offset_px + thunderstorm_nm / pixel_size_nm - 0.5"
        ),
        "axis_order": "x is horizontal/column; y is vertical/row; no x/y swap",
    }
