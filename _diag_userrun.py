# -*- coding: utf-8 -*-
"""_diag_userrun.py — 拉 21:10 任务的 zip+mp4, 分别打分定位坏点。"""
import io
import subprocess
import sys
import zipfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
from experiments import rh_task  # noqa: E402

key = rh_task.load_api_key()
TASK = "2092961966077517825"
OUT = ROOT / "data/swap/hairchain_B/_user_run"
OUT.mkdir(parents=True, exist_ok=True)

urls = rh_task.collect_file_urls(rh_task.task_outputs(key, TASK))
zu = mu = None
for u in urls:
    print("out:", u.split("/output/")[-1])
    if u.endswith(".zip"):
        zu = u
        rh_task.download(u, OUT / "user.zip")
    elif u.endswith(".mp4"):
        mu = u
        rh_task.download(u, OUT / "user.mp4")

# zip 图
with zipfile.ZipFile(OUT / "user.zip") as z:
    for nm in z.namelist():
        with z.open(nm) as fsrc, open(OUT / "user_zipimg.png", "wb") as fdst:
            fdst.write(fsrc.read())
        print("[zip 内]", nm)

# mp4 抽 6/10/14 帧
for n in (6, 10, 14, 30):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(OUT / "user.mp4"),
                    "-vf", f"select='eq(n\\,{n})'", "-vsync", "vfr",
                    "-frames:v", "1", str(OUT / f"user_f{n}.png")],
                   check=True)

# 打分
import cv2  # noqa: E402
from experiments.metrics import FaceComparator  # noqa: E402
fc = FaceComparator()
e_ref = fc.embed(fc.largest_face(cv2.imread(str(ROOT / "in/_ref_ascii.jpg"))))
e_tgt = fc.embed(fc.largest_face(cv2.imread(str(ROOT / "in/_tgt_ascii.jpg"))))
print(f"\n{'产物':<18}{'vs_ref':>9}{'vs_target':>11}")
for p in sorted(OUT.glob("*.png")):
    e = fc.embed(fc.largest_face(cv2.imread(str(p))))
    if e is None:
        print(f"{p.name:<18}{'-':>9}{'no face':>11}")
    else:
        print(f"{p.name:<18}{fc.cosine(e, e_ref):>9.4f}{fc.cosine(e, e_tgt):>11.4f}")
