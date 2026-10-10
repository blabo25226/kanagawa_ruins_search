"""Affine registration with independent validation; no feature detection."""

from .gcp import GCP
from .transform import fit_affine, georeference

__all__ = ["GCP", "fit_affine", "georeference"]
