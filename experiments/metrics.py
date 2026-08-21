"""Face similarity metrics for M5 experiments (YuNet detect + SFace embed).

Pure OpenCV DNN: no insightface/dlib/torch needed. Models (Apache-2.0, opencv_zoo):
    data/models/yunet.onnx   face detection (232 KB)
    data/models/sface.onnx   face embedding  (37 MB)

SFace cosine thresholds (opencv_zoo reference): SIMILARITY >= 0.363, MISMATCH <= 0.316.

API:
    sim = FaceComparator()                       # loads models once
    sim.score(path_a, path_b) -> dict            # cosine/SSIM etc.
"""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "data" / "models"

COS_SIMILAR = 0.363   # opencv_zoo SFace cosine threshold


class FaceComparator:
    def __init__(self, yunet: str | Path | None = None, sface: str | Path | None = None):
        yunet = Path(yunet) if yunet else MODEL_DIR / "yunet.onnx"
        sface = Path(sface) if sface else MODEL_DIR / "sface.onnx"
        if not yunet.exists() or not sface.exists():
            raise FileNotFoundError(
                f"missing model(s): {yunet} / {sface} — see experiments/metrics.py header")
        self.det = cv2.FaceDetectorYN.create(str(yunet), "", (320, 320), score_threshold=0.6)
        self.rec = cv2.FaceRecognizerSF.create(str(sface), "")

    # ---- detection ----

    def largest_face(self, image: np.ndarray) -> np.ndarray | None:
        """Return the aligned 112x112 face crop of the largest detected face, or None."""
        h, w = image.shape[:2]
        size = 320
        self.det.setInputSize((max(w, 1), max(h, 1)))
        _, faces = self.det.detect(image)
        if faces is None or len(faces) == 0:
            # retry down/up-scaled for tiny/huge images
            scale = size / max(w, h)
            if 0.05 < scale < 0.95:
                small = cv2.resize(image, (int(w * scale), int(h * scale)))
                self.det.setInputSize((small.shape[1], small.shape[0]))
                _, faces = self.det.detect(small)
                if faces is not None and len(faces):
                    areas = faces[:, 2] * faces[:, 3]
                    i = int(np.argmax(areas))
                    f = faces[i]
                    f = f.copy()
                    f[[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]] /= scale
                    faces = f.reshape(1, -1)
        if faces is None or len(faces) == 0:
            return None
        areas = faces[:, 2] * faces[:, 3]
        i = int(np.argmax(areas))
        return self.rec.alignCrop(image, faces[i])

    def embed(self, aligned: np.ndarray) -> np.ndarray:
        return self.rec.feature(aligned)

    # ---- scoring ----

    def cosine(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(self.rec.match(a, b, cv2.FaceRecognizerSF_FR_COSINE))

    @staticmethod
    def _gray(img: np.ndarray) -> np.ndarray:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def ssim(self, a: np.ndarray, b: np.ndarray) -> float:
        """Structural similarity on resized grayscale (image-level, not identity)."""
        ga, gb = self._gray(a), self._gray(b)
        h = min(ga.shape[0], gb.shape[0], 512)
        w = min(ga.shape[1], gb.shape[1], 512)
        ga = cv2.resize(ga, (w, h))
        gb = cv2.resize(gb, (w, h))
        ga = ga.astype(np.float64)
        gb = gb.astype(np.float64)
        mu_a, mu_b = ga.mean(), gb.mean()
        va, vb = ga.var(), gb.var()
        cov = ((ga - mu_a) * (gb - mu_b)).mean()
        c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
        return float(((2 * mu_a * mu_b + c1) * (2 * cov + c2)) /
                     ((mu_a ** 2 + mu_b ** 2 + c1) * (va + vb + c2)))

    def score(self, path_a: str | Path, path_b: str | Path) -> dict:
        """Identity similarity between two images (largest face each).

        Returns cosine in [-1, 1] (>=0.363 considered same person by SFace),
        plus face_ok flags, ssim and psnr for diagnostics.
        """
        ia = cv2.imread(str(path_a))
        ib = cv2.imread(str(path_b))
        if ia is None or ib is None:
            return {"face_ok": False, "cosine": None,
                    "error": f"cannot read image(s): {path_a} / {path_b}"}
        fa = self.largest_face(ia)
        fb = self.largest_face(ib)
        if fa is None or fb is None:
            return {"face_ok": False, "cosine": None,
                    "error": "no face detected in " + ("A" if fa is None else "B"),
                    "ssim": self.ssim(ia, ib)}
        ea, eb = self.embed(fa), self.embed(fb)
        cos = self.cosine(ea, eb)
        # psnr between aligned crops (pixel-level)
        diff = fa.astype(np.float64) - fb.astype(np.float64)
        mse = float((diff ** 2).mean())
        psnr = 100.0 if mse <= 1e-9 else 10 * math.log10(255 ** 2 / mse)
        return {
            "face_ok": True,
            "cosine": round(cos, 4),
            "same_person": bool(cos >= COS_SIMILAR),
            "ssim": round(self.ssim(fa, fb), 4),
            "psnr": round(psnr, 2),
        }


if __name__ == "__main__":
    # self-test: compare the first two covers of every raw dir that has both
    import sys

    cmp_ = FaceComparator()
    raw_root = ROOT / "data" / "raw" / "runninghub"
    tested = same = 0
    for d in sorted(raw_root.iterdir()):
        c0, c1 = d / "cover_0.jpg", d / "cover_1.jpg"
        if not (c0.exists() and c1.exists()):
            continue
        r = cmp_.score(c0, c1)
        if r.get("face_ok"):
            tested += 1
            same += int(r["same_person"])
            print(f"{d.name[:44]:46} cos={r['cosine']:+.3f} {'SAME' if r['same_person'] else 'diff'} ssim={r['ssim']:.3f}")
        if tested >= 12:
            break
    print(f"\n[self-test] {tested} cover pairs scored, {same} judged same-person (cover_0 vs cover_1 often differs by design)")
    sys.exit(0)
