"""Minimal INT-30 R2D L10 grazing render parity evidence.

Read-only scope:
- open SURF-20 R5 source and INT-30 R2C candidate;
- create a fresh World node in each render process;
- render only L10/grazing source and candidate plus one side-by-side image;
- write render_contract.json;
- never save either .blend and never export GLB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BLENDER = Path(r"D:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
OUT_DIR = HERE / "work" / "INT_30_20260718_R2D_R1_RENDER_PARITY"
RENDERS_DIR = OUT_DIR / "renders"
REPORTS_DIR = OUT_DIR / "reports"
SOURCE_BLEND = HERE / "work" / "SURF_20_20260718_R5" / "SURF20_R5_FULL_SHELL_MATERIAL_CANDIDATE.blend"
CANDIDATE_BLEND = HERE / "work" / "INT_30_20260718_R2C_R1_MESO_DETAIL_MERGE" / "INT_30_R2C_R1_MESO_DETAIL_MERGE_CANDIDATE.blend"
FORMAL_GLB = ROOT / "高炉前端数据" / "models" / "gl02_blast_furnace.glb"

EXPECTED_SOURCE_SHA = "4f1dae2804300c2c99462b4a5d7967abd9085a3ffd7170ae26af4e105290471b"
EXPECTED_CANDIDATE_SHA = "d1278f85713aaa4af9753fd121b2a889d3086165a03d29790b0f20934c92cbd8"
EXPECTED_FORMAL_GLB_SHA = "808960f1b2703e7fb27df35f1b1b1a17063b9b10d2267acba593fc3872b62af6"

SHELL_OBJECTS = [
    "APPROX_GL02_FURNACE_HEARTH",
    "APPROX_GL02_FURNACE_BOSH",
    "APPROX_GL02_FURNACE_BELLY",
    "APPROX_GL02_FURNACE_SHAFT",
    "APPROX_GL02_FURNACE_THROAT",
]
MESO_OBJECTS = ["APPROX_GL02_shell_stiffener_rings", "APPROX_GL02_P35_shell_welds"]
VISIBLE_OBJECTS = sorted(SHELL_OBJECTS + MESO_OBJECTS)
MATERIAL_NAME = "SURF20_R5_aged_painted_carbon_steel_shared_world"

WORLD_CONTRACT = {
    "name": "INT30_R2D_L10_GRAZING_FAIR_WORLD",
    "use_nodes": True,
    "background_color": [0.01, 0.015, 0.021, 1.0],
    "background_strength": 0.52,
    "surface_link": "Background.Background -> World Output.Surface",
}
COLOR_MANAGEMENT = {
    "view_transform": "AgX",
    "look": "AgX - Medium Low Contrast",
    "exposure": 0.24,
    "gamma": 1.0,
}
RENDER_SETTINGS = {
    "engine": "BLENDER_EEVEE_NEXT",
    "samples": 96,
    "film_transparent": False,
    "resolution": [1440, 900],
}
LIGHTS = [
    {"name": "INT30_R2D_GRAZING_RAKE_LIGHT", "type": "AREA", "location": [-6.0656, -9.3660, 14.0], "rotation": [0.6729335, 0.0, -0.5746997], "energy": 780.0, "size": 1.4, "color": [1.0, 1.0, 1.0]},
    {"name": "INT30_R2D_P40_COOL_FILL", "type": "AREA", "location": [10.7040, -20.5160, 22.0], "rotation": [0.8106582, 0.0, 0.4808874], "energy": 245.0, "size": 10.8824, "color": [1.0, 1.0, 1.0]},
    {"name": "INT30_R2D_P40_SOFT_KEY", "type": "AREA", "location": [-11.15, -25.8680, 28.8], "rotation": [0.7743172, 0.0, -0.4069707], "energy": 1050.0, "size": 5.5304, "color": [1.0, 1.0, 1.0]},
    {"name": "INT30_R2D_P40_TOP_SOFTBOX", "type": "AREA", "location": [0.0, 0.0, 54.0], "rotation": [0.0, 0.0, 0.0], "energy": 185.0, "size": 13.8260, "color": [1.0, 1.0, 1.0]},
]
CAMERA = {
    "layer": "L10",
    "view": "grazing_near",
    "mode": "look_at",
    "location": [5.8, -7.2, 3.16],
    "target": [3.25, -0.15, 2.91],
    "ortho": 3.4,
    "clip_start": 0.05,
    "clip_end": 1000.0,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_payload(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def host_main() -> int:
    if not BLENDER.is_file():
        raise FileNotFoundError(BLENDER)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RENDERS_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)

    source_before = sha256_file(SOURCE_BLEND)
    candidate_before = sha256_file(CANDIDATE_BLEND)
    formal_before = sha256_file(FORMAL_GLB)
    if source_before != EXPECTED_SOURCE_SHA:
        raise RuntimeError(f"source SHA mismatch: {source_before}")
    if candidate_before != EXPECTED_CANDIDATE_SHA:
        raise RuntimeError(f"candidate SHA mismatch: {candidate_before}")
    if formal_before != EXPECTED_FORMAL_GLB_SHA:
        raise RuntimeError(f"formal GLB SHA mismatch: {formal_before}")

    commands = []
    for kind, blend in [("source", SOURCE_BLEND), ("candidate", CANDIDATE_BLEND)]:
        command = [
            str(BLENDER),
            "--background",
            str(blend),
            "--python",
            str(Path(__file__).resolve()),
            "--",
            "--render-kind",
            kind,
        ]
        proc = subprocess.run(command, cwd=str(HERE), capture_output=True, text=True)
        write_text(REPORTS_DIR / f"{kind}.stdout.log", proc.stdout)
        write_text(REPORTS_DIR / f"{kind}.stderr.log", proc.stderr)
        commands.append({"kind": kind, "blend": str(blend), "command": command, "returncode": proc.returncode})
        if proc.returncode != 0 or "Traceback (most recent call last)" in proc.stderr:
            raise RuntimeError(f"{kind} render failed; see {REPORTS_DIR}")

    side_by_side = compose_side_by_side()
    source_after = sha256_file(SOURCE_BLEND)
    candidate_after = sha256_file(CANDIDATE_BLEND)
    formal_after = sha256_file(FORMAL_GLB)
    source_png = RENDERS_DIR / "INT30_R2D_L10_GRAZING_SOURCE.png"
    candidate_png = RENDERS_DIR / "INT30_R2D_L10_GRAZING_CANDIDATE.png"
    contract = {
        "schema_version": "bf3d.int30_r2d.l10_grazing_render_contract.v1",
        "stage": "INT-30_R2D_R1_RENDER_PARITY_MINIMAL_L10_GRAZING",
        "generated_at": now_iso(),
        "scope": "minimal L10 grazing source/candidate render parity only; no blend save, no GLB export, no pipeline update",
        "inputs": {
            "source_blend": {"path": rel(SOURCE_BLEND), "sha256_before": source_before, "sha256_after": source_after, "unchanged": source_before == source_after},
            "candidate_blend": {"path": rel(CANDIDATE_BLEND), "sha256_before": candidate_before, "sha256_after": candidate_after, "unchanged": candidate_before == candidate_after},
            "formal_glb": {"path": rel(FORMAL_GLB), "sha256_before": formal_before, "sha256_after": formal_after, "unchanged": formal_before == formal_after},
        },
        "fair_render_contract": {
            "world": WORLD_CONTRACT,
            "world_hash": hash_payload(WORLD_CONTRACT),
            "color_management": COLOR_MANAGEMENT,
            "color_management_hash": hash_payload(COLOR_MANAGEMENT),
            "render_settings": RENDER_SETTINGS,
            "render_settings_hash": hash_payload(RENDER_SETTINGS),
            "lights": LIGHTS,
            "lights_hash": hash_payload(LIGHTS),
            "camera": CAMERA,
            "camera_hash": hash_payload(CAMERA),
            "visible_objects": VISIBLE_OBJECTS,
            "visible_objects_hash": hash_payload(VISIBLE_OBJECTS),
            "hidden_policy": "all non-camera/non-light objects hidden except five shell objects plus rings/welds; sensors and pressure are hidden",
        },
        "renders": {
            "source": file_record(source_png),
            "candidate": file_record(candidate_png),
            "side_by_side": file_record(side_by_side),
        },
        "commands": commands,
        "assertions": {
            "source_blend_unchanged": source_before == source_after == EXPECTED_SOURCE_SHA,
            "candidate_blend_unchanged": candidate_before == candidate_after == EXPECTED_CANDIDATE_SHA,
            "formal_glb_unchanged": formal_before == formal_after == EXPECTED_FORMAL_GLB_SHA,
            "only_expected_pngs": sorted(p.name for p in RENDERS_DIR.glob("*.png")) == sorted([source_png.name, candidate_png.name, side_by_side.name]),
            "no_blend_output": not any(OUT_DIR.rglob("*.blend")) and not any(OUT_DIR.rglob("*.blend1")),
            "no_glb_output": not any(OUT_DIR.rglob("*.glb")),
        },
    }
    contract["assertions"]["pass"] = all(contract["assertions"].values())
    write_json(OUT_DIR / "render_contract.json", contract)
    if not contract["assertions"]["pass"]:
        raise RuntimeError("minimal render contract assertions failed")
    print(json.dumps({"status": "minimal_l10_grazing_done", "side_by_side": rel(side_by_side)}, ensure_ascii=False))
    return 0


def file_record(path: Path) -> dict[str, Any]:
    return {"path": rel(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def compose_side_by_side() -> Path:
    from PIL import Image, ImageDraw, ImageFont

    source = Image.open(RENDERS_DIR / "INT30_R2D_L10_GRAZING_SOURCE.png").convert("RGBA").resize((720, 450))
    candidate = Image.open(RENDERS_DIR / "INT30_R2D_L10_GRAZING_CANDIDATE.png").convert("RGBA").resize((720, 450))
    canvas = Image.new("RGBA", (1440, 530), (8, 10, 10, 255))
    canvas.paste(source, (0, 80))
    canvas.paste(candidate, (720, 80))
    draw = ImageDraw.Draw(canvas)
    font_big = load_font(ImageFont, 34)
    font_med = load_font(ImageFont, 22)
    draw.rectangle((0, 0, 1440, 80), fill=(0, 0, 0, 230))
    draw.text((16, 14), "R2D L10 GRAZING", fill=(255, 150, 58, 255), font=font_big)
    draw.text((380, 25), "fresh World nodes: color=(0.01,0.015,0.021), strength=0.52; AgX .24; EEVEE96; four fixed lights", fill=(232, 242, 236, 255), font=font_med)
    draw.text((18, 94), "SOURCE SURF-20 R5", fill=(255, 150, 58, 255), font=font_med)
    draw.text((738, 94), "R2C CANDIDATE", fill=(255, 150, 58, 255), font=font_med)
    out = RENDERS_DIR / "INT30_R2D_L10_GRAZING_SOURCE_VS_CANDIDATE.png"
    canvas.save(out)
    return out


def load_font(image_font_module: Any, size: int) -> Any:
    for path in [r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\msyh.ttc"]:
        if Path(path).is_file():
            return image_font_module.truetype(path, size)
    return image_font_module.load_default()


def blender_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-kind", choices=["source", "candidate"], required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    import bpy
    from mathutils import Vector

    scene = bpy.context.scene
    enum_ids = {item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items}
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in enum_ids else "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = RENDER_SETTINGS["resolution"]
    scene.render.film_transparent = False
    scene.view_settings.view_transform = COLOR_MANAGEMENT["view_transform"]
    scene.view_settings.look = COLOR_MANAGEMENT["look"]
    scene.view_settings.exposure = COLOR_MANAGEMENT["exposure"]
    scene.view_settings.gamma = COLOR_MANAGEMENT["gamma"]
    eevee = getattr(scene, "eevee", None)
    if eevee is not None:
        for attr in ("taa_render_samples", "taa_samples"):
            if hasattr(eevee, attr):
                setattr(eevee, attr, RENDER_SETTINGS["samples"])

    world = bpy.data.worlds.new(WORLD_CONTRACT["name"])
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new(type="ShaderNodeBackground")
    bg.inputs["Color"].default_value = WORLD_CONTRACT["background_color"]
    bg.inputs["Strength"].default_value = WORLD_CONTRACT["background_strength"]
    out = nt.nodes.new(type="ShaderNodeOutputWorld")
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    scene.world = world

    for obj in bpy.data.objects:
        if obj.type == "LIGHT":
            obj.hide_viewport = True
            obj.hide_render = True
        elif obj.type != "CAMERA":
            visible = obj.name in VISIBLE_OBJECTS
            obj.hide_viewport = not visible
            obj.hide_render = not visible
    for spec in LIGHTS:
        data = bpy.data.lights.new(spec["name"], spec["type"])
        data.energy = spec["energy"]
        data.color = spec["color"]
        data.size = spec["size"]
        obj = bpy.data.objects.new(spec["name"], data)
        scene.collection.objects.link(obj)
        obj.location = spec["location"]
        obj.rotation_euler = spec["rotation"]

    cam_data = bpy.data.cameras.new("INT30_R2D_L10_GRAZING_CAMERA_DATA")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = CAMERA["ortho"]
    cam_data.clip_start = CAMERA["clip_start"]
    cam_data.clip_end = CAMERA["clip_end"]
    cam = bpy.data.objects.new("INT30_R2D_L10_GRAZING_CAMERA", cam_data)
    scene.collection.objects.link(cam)
    cam.location = CAMERA["location"]
    direction = Vector(CAMERA["target"]) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    if bpy.data.materials.get(MATERIAL_NAME) is None:
        raise RuntimeError(f"missing material: {MATERIAL_NAME}")
    missing = [name for name in VISIBLE_OBJECTS if bpy.data.objects.get(name) is None]
    if missing:
        raise RuntimeError(f"missing visible objects: {missing}")

    out_path = RENDERS_DIR / f"INT30_R2D_L10_GRAZING_{args.render_kind.upper()}.png"
    scene.render.filepath = str(out_path)
    bpy.ops.render.render(write_still=True)
    return 0


if __name__ == "__main__":
    if "--" in sys.argv:
        raise SystemExit(blender_main())
    raise SystemExit(host_main())
