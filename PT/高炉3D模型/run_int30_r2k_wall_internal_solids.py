import subprocess
from pathlib import Path


ROOT = Path(r"D:\文件\冀南钢铁运行中第二版本")
BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
STAGE = ROOT / "PT" / "高炉3D模型" / "work" / "INT_30_20260719_R2K_WALL_INTERNAL_SOLIDS"
SCRIPT = STAGE / "scripts" / "r2k_build_wall_internal_solids.py"
LOG = STAGE / "logs" / "run_blender_build.log"


def main():
    STAGE.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(BLENDER), "--background", "--python-exit-code", "1", "--python", str(SCRIPT)]
    with LOG.open("w", encoding="utf-8") as f:
        f.write(" ".join(cmd) + "\n")
        f.flush()
        proc = subprocess.run(cmd, cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT, text=True)
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
