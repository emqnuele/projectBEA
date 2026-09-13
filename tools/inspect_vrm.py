"""What a .vrm or .vrma actually contains, and what its licence allows.

A VRM carries its own terms of use inside the file — who may use the avatar,
whether commercial use is allowed, whether it may be redistributed. That is
worth reading *before* you put a model on stream, and it is the only model
format that lets you.

    uv run python tools/inspect_vrm.py data/models/bea.vrm
"""

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any, Dict

GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A

# the five emotions and the five mouth shapes VRM 1.0 standardises
EMOTIONS = ("happy", "angry", "sad", "relaxed", "surprised", "neutral")
VISEMES = ("aa", "ih", "ou", "ee", "oh")

# what the licence fields mean, in words rather than enum values
MEANING = {
    "avatarPermission": {
        "onlyAuthor": "only the author may use this avatar",
        "onlySeparatelyLicensedPerson": "only people licensed separately by the author",
        "everyone": "anyone may use this avatar",
    },
    "commercialUsage": {
        "personalNonProfit": "personal, non-profit use only",
        "personalProfit": "an individual may use it commercially",
        "corporation": "companies may use it commercially",
    },
    "creditNotation": {
        "required": "you must credit the author",
        "unnecessary": "no credit required",
    },
}


def gltf_json(path: Path) -> Dict[str, Any]:
    """The JSON chunk of a GLB container. Both .vrm and .vrma are GLB files."""
    raw = path.read_bytes()
    if len(raw) < 12:
        raise ValueError(f"{path.name} is too small to be a glTF binary")
    magic, _version, total = struct.unpack_from("<III", raw, 0)
    if magic != GLB_MAGIC:
        raise ValueError(f"{path.name} is not a glTF binary (.vrm/.vrma/.glb)")

    offset = 12
    while offset < min(total, len(raw)):
        length, kind = struct.unpack_from("<II", raw, offset)
        offset += 8
        if kind == CHUNK_JSON:
            return json.loads(raw[offset:offset + length].decode("utf-8"))
        offset += length
    raise ValueError(f"{path.name} has no JSON chunk")


def triangles(gltf: Dict[str, Any]) -> int:
    accessors = gltf.get("accessors", [])
    total = 0
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            index = primitive.get("indices")
            if index is not None and index < len(accessors):
                total += accessors[index].get("count", 0) // 3
    return total


def report_model(path: Path, gltf: Dict[str, Any]) -> int:
    """Prints what the file is and returns the number of problems found."""
    problems = 0
    extensions = gltf.get("extensions", {})
    vrm1 = extensions.get("VRMC_vrm")
    vrm0 = extensions.get("VRM")

    if not vrm1 and not vrm0:
        print("  NOT a VRM. It is a plain glTF/GLB: no standard bone names, no")
        print("  standard expressions, so nothing can be mapped onto it.")
        print("  Convert it to VRM first (UniVRM in Unity, or the Blender VRM add-on).")
        return 1

    if vrm0:
        print("  VRM 0.x — supported, and turned to face the camera automatically.")
        groups = vrm0.get("blendShapeMaster", {}).get("blendShapeGroups", [])
        names = [g.get("presetName") or g.get("name") for g in groups]
        print(f"  blend shape groups: {', '.join(n for n in names if n) or 'NONE'}")
        return problems

    print(f"  VRM {vrm1.get('specVersion', '1.0')}")

    meta = vrm1.get("meta", {})
    print("\n  Licence, as the file itself declares it")
    print(f"    name:     {meta.get('name', '(unnamed)')}")
    print(f"    authors:  {', '.join(meta.get('authors', [])) or '(none)'}")
    for key in ("avatarPermission", "commercialUsage", "creditNotation"):
        value = meta.get(key)
        if value is not None:
            print(f"    {key}: {value} — {MEANING.get(key, {}).get(value, '?')}")
    redistribution = meta.get("allowRedistribution")
    if redistribution is not None:
        allowed = "yes" if redistribution else "NO"
        print(f"    allowRedistribution: {allowed}"
              + ("" if redistribution else "  <- do not commit this file"))
    if meta.get("licenseUrl"):
        print(f"    licenceUrl: {meta['licenseUrl']}")

    bones = vrm1.get("humanoid", {}).get("humanBones", {})
    print(f"\n  Rig: {len(bones)} humanoid bones")
    for required in ("hips", "spine", "head"):
        if required not in bones:
            print(f"    MISSING {required} — clips and framing will not work")
            problems += 1

    preset = vrm1.get("expressions", {}).get("preset", {})
    emotions = [n for n in EMOTIONS if n in preset]
    visemes = [n for n in VISEMES if n in preset]
    print(f"\n  Expressions: {len(preset)} presets")
    print(f"    emotions: {', '.join(emotions) or 'NONE'}")
    print(f"    visemes:  {', '.join(visemes) or 'NONE'}")
    if not emotions:
        print("    She will have one face for every mood.")
        problems += 1
    if "aa" not in preset:
        print("    No 'aa' viseme: her mouth cannot move while she talks.")
        problems += 1

    print(f"\n  Geometry: {triangles(gltf):,} triangles, "
          f"{len(gltf.get('textures', []))} textures, "
          f"{path.stat().st_size / 1e6:.2f} MB")
    return problems


def report_clip(path: Path, gltf: Dict[str, Any]) -> int:
    animation = gltf["extensions"]["VRMC_vrm_animation"]
    bones = animation.get("humanoid", {}).get("humanBones", {})
    expressions = list(animation.get("expressions", {}).get("preset", {}))

    print(f"  VRM Animation {animation.get('specVersion', '1.0')}")
    print(f"  {len(bones)} humanoid bones driven by standard name, so it plays on")
    print("  any VRM — which is why clips can ship with projectBEA and models cannot.")
    if expressions:
        print(f"  expressions driven: {', '.join(expressions)}")
    if "lookAt" in animation:
        print("  drives where she looks")

    channels = sum(len(a.get("channels", [])) for a in gltf.get("animations", []))
    print(f"  {channels} channels, {path.stat().st_size / 1024:.1f} KB")
    if channels < 10:
        print("  Few channels: everything it does not drive stays in the rest pose")
        print("  (the T-pose arms). A full idle clip animates all of them.")
    return 0


def inspect(path: Path) -> int:
    print(f"\n=== {path.name} ===")
    try:
        gltf = gltf_json(path)
    except (ValueError, OSError) as e:
        print(f"  {e}")
        return 1

    if "VRMC_vrm_animation" in gltf.get("extensions", {}):
        return report_clip(path, gltf)
    return report_model(path, gltf)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read what a .vrm model or .vrma clip contains, and what its licence allows.",
    )
    parser.add_argument("files", nargs="+", type=Path, help=".vrm or .vrma files")
    args = parser.parse_args()

    problems = 0
    for path in args.files:
        if not path.is_file():
            print(f"\n=== {path} ===\n  not found")
            problems += 1
            continue
        problems += inspect(path)

    print()
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
