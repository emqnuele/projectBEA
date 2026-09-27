"""What a .vrm or .vrma file contains, read straight from its GLB container.

A VRM carries its own terms of use — who may use the avatar, whether it may be
used commercially or redistributed, whether credit is owed — and its own
thumbnail. Both are read here without loading a single mesh: only the JSON
chunk is parsed, and the thumbnail is one slice of the binary chunk.

Used by `tools/inspect_vrm.py`, by the doctor and by the model library in the
dashboard, so all three describe a file the same way.
"""

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942

# the five emotions and the five mouth shapes VRM 1.0 standardises
EMOTIONS = ("happy", "angry", "sad", "relaxed", "surprised", "neutral")
VISEMES = ("aa", "ih", "ou", "ee", "oh")

# the same table three-vrm loads 0.x files with; a group outside it keeps its own name
V0_PRESETS = {
    "a": "aa", "e": "ee", "i": "ih", "o": "oh", "u": "ou",
    "blink": "blink", "joy": "happy", "angry": "angry", "sorrow": "sad", "fun": "relaxed",
    "lookup": "lookUp", "lookdown": "lookDown", "lookleft": "lookLeft", "lookright": "lookRight",
    "blink_l": "blinkLeft", "blink_r": "blinkRight", "neutral": "neutral",
}

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


@dataclass(frozen=True)
class Blob:
    """Where the binary chunk sits in the file, so a slice of it can be read alone."""

    path: Path
    offset: int
    length: int

    def read(self, start: int, length: int) -> bytes:
        if start < self.offset or start + length > self.offset + self.length:
            raise ValueError("that range is outside the binary chunk")
        with open(self.path, "rb") as f:
            f.seek(start)
            return f.read(length)


def read_glb(path: Path) -> Tuple[Dict[str, Any], Optional[Blob]]:
    """The JSON chunk of a GLB container, and where its binary chunk is."""
    with open(path, "rb") as f:
        header = f.read(12)
        if len(header) < 12:
            raise ValueError(f"{path.name} is too small to be a glTF binary")
        magic, _version, total = struct.unpack("<III", header)
        if magic != GLB_MAGIC:
            raise ValueError(f"{path.name} is not a glTF binary (.vrm/.vrma/.glb)")

        doc: Optional[Dict[str, Any]] = None
        blob: Optional[Blob] = None
        offset = 12
        while offset + 8 <= total:
            f.seek(offset)
            chunk = f.read(8)
            if len(chunk) < 8:
                break
            length, kind = struct.unpack("<II", chunk)
            if kind == CHUNK_JSON and doc is None:
                doc = json.loads(f.read(length).decode("utf-8"))
            elif kind == CHUNK_BIN and blob is None:
                blob = Blob(path, offset + 8, length)
            offset += 8 + length

    if doc is None:
        raise ValueError(f"{path.name} has no JSON chunk")
    return doc, blob


def gltf_json(path: Path) -> Dict[str, Any]:
    return read_glb(path)[0]


def triangles(gltf: Dict[str, Any]) -> int:
    accessors = gltf.get("accessors", [])
    total = 0
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            index = primitive.get("indices")
            if index is not None and index < len(accessors):
                total += accessors[index].get("count", 0) // 3
    return total


def is_vrm(gltf: Dict[str, Any]) -> bool:
    extensions = gltf.get("extensions", {})
    return "VRMC_vrm" in extensions or "VRM" in extensions


def is_clip(gltf: Dict[str, Any]) -> bool:
    return "VRMC_vrm_animation" in gltf.get("extensions", {})


def expression_names(gltf: Dict[str, Any]) -> List[str]:
    """The expressions the renderer will find on this model, under its names for them."""
    extensions = gltf.get("extensions", {})
    vrm1 = extensions.get("VRMC_vrm")
    if vrm1:
        expressions = vrm1.get("expressions", {})
        return list(expressions.get("preset", {})) + list(expressions.get("custom", {}))
    vrm0 = extensions.get("VRM") or {}
    names = []
    for group in vrm0.get("blendShapeMaster", {}).get("blendShapeGroups", []):
        name = V0_PRESETS.get(group.get("presetName") or "") or group.get("name")
        if name:
            names.append(name)
    return names


def thumbnail(path: Path) -> Optional[Tuple[str, bytes]]:
    """The picture the file embeds of itself, as (mime type, bytes), or None."""
    doc, blob = read_glb(path)
    if blob is None:
        return None
    extensions = doc.get("extensions", {})
    image: Optional[int]
    # vrm 1.0 points at an image, vrm 0.x at a texture that points at one
    if "VRMC_vrm" in extensions:
        image = extensions["VRMC_vrm"].get("meta", {}).get("thumbnailImage")
    else:
        texture = (extensions.get("VRM") or {}).get("meta", {}).get("texture")
        textures = doc.get("textures", [])
        image = (textures[texture].get("source")
                 if isinstance(texture, int) and 0 <= texture < len(textures) else None)
    images = doc.get("images", [])
    if not isinstance(image, int) or not 0 <= image < len(images):
        return None
    img = images[image]
    views = doc.get("bufferViews", [])
    index = img.get("bufferView")
    if not isinstance(index, int) or not 0 <= index < len(views):
        return None
    view = views[index]
    start = blob.offset + int(view.get("byteOffset", 0))
    return img.get("mimeType", "image/png"), blob.read(start, int(view["byteLength"]))


def _licence_v1(meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "avatar_permission": meta.get("avatarPermission"),
        "commercial": meta.get("commercialUsage"),
        "credit_required": meta.get("creditNotation") == "required",
        "redistribution": meta.get("allowRedistribution"),
        "modification": meta.get("modification"),
        "url": meta.get("otherLicenseUrl") or meta.get("licenseUrl") or "",
    }


def _licence_v0(meta: Dict[str, Any]) -> Dict[str, Any]:
    # 0.x keeps the vroid hub terms as query parameters of this url
    url = meta.get("otherPermissionUrl") or meta.get("otherLicenseUrl") or ""
    terms: Dict[str, str] = {}
    if "?" in url:
        from urllib.parse import parse_qsl, urlsplit
        terms = dict(parse_qsl(urlsplit(url).query))
    licence = meta.get("licenseName") or ""
    redistribution: Optional[bool] = None
    if "redistribution" in terms:
        redistribution = terms["redistribution"] == "allow"
    elif licence == "Redistribution_Prohibited":
        redistribution = False
    elif licence.startswith("CC"):
        redistribution = True
    credit = terms.get("credit")
    return {
        "avatar_permission": meta.get("allowedUserName"),
        "commercial": meta.get("commercialUssageName"),
        "credit_required": credit == "required" or licence.startswith("CC_BY"),
        "redistribution": redistribution,
        "modification": terms.get("modification"),
        "url": url,
    }


def describe(path: Path) -> Dict[str, Any]:
    """Everything the library shows about one file, without loading its meshes."""
    doc, _blob = read_glb(path)
    extensions = doc.get("extensions", {})
    vrm1 = extensions.get("VRMC_vrm")
    vrm0 = extensions.get("VRM")
    out: Dict[str, Any] = {"size": path.stat().st_size, "vrm": None}
    if not vrm1 and not vrm0:
        return out

    names = expression_names(doc)
    if vrm1:
        meta = vrm1.get("meta", {})
        out.update(vrm="1.0", title=meta.get("name") or "", authors=list(meta.get("authors") or []),
                   licence=_licence_v1(meta),
                   bones=len(vrm1.get("humanoid", {}).get("humanBones", {})))
    else:
        meta = (vrm0 or {}).get("meta", {})
        author = meta.get("author") or ""
        out.update(vrm="0.x", title=meta.get("title") or "", authors=[author] if author else [],
                   licence=_licence_v0(meta),
                   bones=len((vrm0 or {}).get("humanoid", {}).get("humanBones", [])))
    out["emotions"] = [n for n in EMOTIONS if n in names]
    out["visemes"] = [n for n in VISEMES if n in names]
    out["has_thumbnail"] = thumbnail(path) is not None
    warnings = []
    if "aa" not in names:
        warnings.append("No 'aa' mouth shape: her mouth will not move while she talks.")
    missing = [n for n in EMOTIONS if n != "neutral" and n not in names]
    if missing:
        warnings.append(f"No {', '.join(missing)} expression: those moods will not show on her face.")
    out["warnings"] = warnings
    return out
