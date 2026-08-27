# -*- coding: utf-8 -*-
"""_diag_consistency.py — 一致性诊断: 视频帧 vs 各版直出图, 统一 insightface 打分。"""
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analyzer"))
sys.path.insert(0, str(ROOT / "experiments"))

B = ROOT / "data/swap/hairchain_B"

# 1) 解 zip 图
zimg = B / "_zip_img.png"
with zipfile.ZipFile(B / "scail2_final.zip") as z:
    names = z.namelist()
    print("[zip 内]", names)
    with z.open(names[0]) as fsrc, open(zimg, "wb") as fdst:
        fdst.write(fsrc.read())

# 2) sc_0.mp4(视频版) 抽 0/4/8/12/16/19 帧
for n in (0, 4, 8, 12, 16, 19):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(B / "sc_0.mp4"),
                    "-vf", f"select='eq(n\\,{n})'", "-vsync", "vfr",
                    "-frames:v", "1", str(B / f"_sc_f{n:02d}.png")],
                   check=True)

# 3) 统一打分(内联, 不 import 会劫持 stdout 的 _task_hair_eval)
import cv2  # noqa: E402
import swap_face as sf  # noqa: E402
from experiments.metrics import FaceComparator  # noqa: E402

REF = ROOT / "in/_ref_ascii.jpg"
TGT = ROOT / "in/_tgt_ascii.jpg"
fc = FaceComparator()
_e_ref = fc.embed(fc.largest_face(cv2.imread(str(REF))))
_e_tgt = fc.embed(fc.largest_face(cv2.imread(str(TGT))))


def score(p: Path) -> dict:
    e = fc.embed(fc.largest_face(cv2.imread(str(p))))
    if e is None:
        return {"identity_vs_ref": None}
    out = {"identity_vs_ref": round(float(fc.cosine(e, _e_ref)), 4),
           "identity_vs_target": round(float(fc.cosine(e, _e_tgt)), 4)}
    h_ref, h = sf._hair_hist(fc, REF), sf._hair_hist(fc, p)
    if h_ref is not None and h is not None:
        out["hair_vs_ref"] = round(sf._hist_intersection(h, h_ref), 3)
    return out
targets = {
    "S_01(视频版交付帧6)": B / "S_01.png",
    "S_03(视频版交付帧14)": B / "S_03.png",
    "native(二版直出)": B / "scail2_native_frame.png",
    "direct(直出B)": B / "scail2_direct_frame.png",
    "zip(三版batch14)": zimg,
}
for n in (0, 4, 8, 12, 16, 19):
    targets[f"sc视频帧{n}"] = B / f"_sc_f{n:02d}.png"

rows = []
for label, p in targets.items():
    if not p.exists():
        rows.append((label, None, "missing"))
        continue
    try:
        m = score(p)
        rows.append((label, m.get("identity_vs_ref"),
                     f"hair_ref={m.get('hair_vs_ref')} vs_tgt={m.get('identity_vs_target')}"))
    except Exception as e:
        rows.append((label, None, repr(e)[:60]))

out_lines = [f"{'product':<24} {'identity_vs_ref':>15}   note (line=0.363, video baseline=0.584-0.602)"]
for label, ident, note in rows:
    v = f"{ident:.4f}" if isinstance(ident, float) else "-"
    out_lines.append(f"{label:<24} {v:>15}   {note}")
report = "\n".join(out_lines)
print(report)

(ROOT / "_diag_consistency.json").write_text(
    json.dumps([{"label": l, "identity_vs_ref": i, "note": n}
                for l, i, n in rows], ensure_ascii=False, indent=1),
    encoding="utf-8")
