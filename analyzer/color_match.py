"""color_match.py — deterministic face-region color/lighting harmonizer.

Fixes the classic inpaint artifact: swapped-in face rendered with slightly
different exposure/color than the host scene. Statistics (mean/std of L,a,b)
computed on the face bbox region of BOTH images are matched, and the
correction is applied through a feathered elliptical mask so the scene keeps
its original grade outside the face.

This is a local, coin-free operator; intended as a reusable Composer
post-step (same spirit as recipes.json ops).

CLI:
    python analyzer/color_match.py <swapped.png> <host_scene.jpg> [-o out.png]
                                   [--margin 0.4] [--strength 1.0]
Prints the LAB deltas applied (proof of effect). Output default:
    <swapped_stem>_cm.png next to the input.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from experiments.metrics import FaceComparator  # noqa: E402


def _face_bbox(fc: FaceComparator, img: np.ndarray) -> tuple[int, int, int, int] | None:
    h, w = img.shape[:2]
    fc.det.setInputSize((w, h))
    _, faces = fc.det.detect(img)
    if faces is None or len(faces) == 0:
        return None
    areas = faces[:, 2] * faces[:, 3]
    f = faces[int(np.argmax(areas))]
    return int(f[0]), int(f[1]), int(f[2]), int(f[3])


def _region_stats(lab: np.ndarray, bbox, margin: float) -> tuple[np.ndarray, ...]:
    x, y, w, h = bbox
    x0, y0 = max(0, int(x - margin * w)), max(0, int(y - margin * h))
    x1 = min(lab.shape[1], int(x + (1 + margin) * w))
    y1 = min(lab.shape[0], int(y + (1 + margin) * h))
    region = lab[y0:y1, x0:x1].reshape(-1, 3).astype(np.float32)
    return region.mean(0), region.std(0) + 1e-6


def _feather_mask(shape, bbox, margin: float) -> np.ndarray:
    x, y, w, h = bbox
    H, W = shape[:2]
    m = np.zeros((H, W), np.float32)
    cx, cy = x + w / 2, y + h / 2
    # ellipse slightly larger than face box
    ax, ay = (1 + margin) * w / 2, (1 + margin) * h / 2
    yy, xx = np.mgrid[0:H, 0:W]
    inside = (((xx - cx) / ax) ** 2 + ((yy - cy) / ay) ** 2) <= 1.0
    m[inside] = 1.0
    return cv2.GaussianBlur(m, (0, 0), sigmaX=max(w, h) * 0.12)


def color_match(swapped_path: Path, host_path: Path, out_path: Path,
                margin: float = 0.4, strength: float = 1.0) -> dict:
    fc = FaceComparator()
    sw = cv2.imread(str(swapped_path))
    host = cv2.imread(str(host_path))
    if sw is None or host is None:
        raise SystemExit(f"unreadable image: {swapped_path} / {host_path}")
    b_sw = _face_bbox(fc, sw)
    b_host = _face_bbox(fc, host)
    if b_sw is None or b_host is None:
        raise SystemExit("no face detected in one of the images")

    lab_sw = cv2.cvtColor(sw, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab_host = cv2.cvtColor(host, cv2.COLOR_BGR2LAB).astype(np.float32)
    mu_s, sd_s = _region_stats(lab_sw, b_sw, margin)
    mu_h, sd_h = _region_stats(lab_host, b_host, margin)

    # match: x' = (x - mu_s)/sd_s * sd_h + mu_h ; blend by strength
    scale = (1 - strength) + strength * (sd_h / sd_s)
    shift = strength * (mu_h - mu_s * (sd_h / sd_s))
    corrected = lab_sw * scale + shift
    corrected = np.clip(corrected, 0, 255)

    mask = _feather_mask(sw.shape, b_sw, margin)[..., None]
    blended = lab_sw * (1 - mask) + corrected * mask
    out = cv2.cvtColor(np.clip(blended, 0, 255).astype(np.uint8),
                       cv2.COLOR_LAB2BGR)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), out)
    return {"out": str(out_path),
            "delta_mu_Lab": [round(float(v), 1) for v in (mu_h - mu_s)],
            "ratio_sd_Lab": [round(float(v), 3) for v in (sd_h / sd_s)],
            "face_bbox": b_sw}


def main() -> int:
    ap = argparse.ArgumentParser(description="face-region LAB color harmonizer")
    ap.add_argument("swapped", help="换脸输出图")
    ap.add_argument("host", help="被换脸原图 (光影基准)")
    ap.add_argument("-o", "--out", default="")
    ap.add_argument("--margin", type=float, default=0.4)
    ap.add_argument("--strength", type=float, default=1.0)
    args = ap.parse_args()
    sw, host = Path(args.swapped), Path(args.host)
    out = Path(args.out) if args.out else sw.with_name(sw.stem + "_cm.png")
    info = color_match(sw, host, out, args.margin, args.strength)
    print(f"[color_match] {info['out']}")
    print(f"[color_match] applied LAB delta(mu)={info['delta_mu_Lab']} "
          f"ratio(sd)={info['ratio_sd_Lab']} bbox={info['face_bbox']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
