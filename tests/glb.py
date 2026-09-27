"""Tiny GLB files built in memory, so no test needs a real 20 MB model."""

import json
import struct
from pathlib import Path
from typing import Any, Dict, Optional

MAGIC = 0x46546C67
JSON = 0x4E4F534A
BIN = 0x004E4942

PNG = b"\x89PNG\r\n\x1a\n" + b"a thumbnail, as far as anyone here is concerned"


def _pad(data: bytes, fill: bytes) -> bytes:
    return data + fill * (-len(data) % 4)


def glb(doc: Dict[str, Any], binary: Optional[bytes] = None) -> bytes:
    body = _pad(json.dumps(doc).encode("utf-8"), b" ")
    chunks = struct.pack("<II", len(body), JSON) + body
    if binary is not None:
        data = _pad(binary, b"\0")
        chunks += struct.pack("<II", len(data), BIN) + data
    return struct.pack("<III", MAGIC, 2, 12 + len(chunks)) + chunks


def vrm1(path: Path, *, presets=("happy", "angry", "sad", "relaxed", "surprised", "neutral", "aa"),
         thumbnail: Optional[bytes] = PNG, credit: str = "unnecessary", name: str = "Bea") -> Path:
    # a leading pad before the image proves the byteOffset is honoured
    pad = b"\0" * 8
    meta: Dict[str, Any] = {
        "name": name, "authors": ["someone"], "avatarPermission": "everyone",
        "commercialUsage": "corporation", "creditNotation": credit, "allowRedistribution": True,
        "modification": "allowModificationRedistribution",
    }
    doc: Dict[str, Any] = {
        "asset": {"version": "2.0"},
        "extensions": {"VRMC_vrm": {
            "specVersion": "1.0", "meta": meta,
            "humanoid": {"humanBones": {b: {"node": 0} for b in ("hips", "spine", "head")}},
            "expressions": {"preset": {p: {} for p in presets}},
        }},
    }
    binary = None
    if thumbnail is not None:
        meta["thumbnailImage"] = 0
        doc["images"] = [{"bufferView": 0, "mimeType": "image/png"}]
        doc["bufferViews"] = [{"buffer": 0, "byteOffset": len(pad), "byteLength": len(thumbnail)}]
        binary = pad + thumbnail
    path.write_bytes(glb(doc, binary))
    return path


def vrm0(path: Path, *, thumbnail: Optional[bytes] = PNG) -> Path:
    groups = [{"name": n.title(), "presetName": p} for n, p in (
        ("a", "a"), ("joy", "joy"), ("angry", "angry"), ("sorrow", "sorrow"), ("fun", "fun"),
        ("neutral", "neutral"))]
    # vroid exports surprised as a custom group, which three-vrm keeps under its own name
    groups.append({"name": "Surprised", "presetName": "unknown"})
    meta: Dict[str, Any] = {
        "title": "Old Bea", "author": "someone", "allowedUserName": "Everyone",
        "commercialUssageName": "Allow", "licenseName": "Other",
        "otherPermissionUrl": "https://hub.vroid.com/license?credit=required&redistribution=allow",
    }
    doc: Dict[str, Any] = {
        "asset": {"version": "2.0"},
        "extensions": {"VRM": {"meta": meta, "humanoid": {"humanBones": [{"bone": "hips"}]},
                               "blendShapeMaster": {"blendShapeGroups": groups}}},
    }
    binary = None
    if thumbnail is not None:
        meta["texture"] = 0
        doc["textures"] = [{"source": 0}]
        doc["images"] = [{"bufferView": 0, "mimeType": "image/png"}]
        doc["bufferViews"] = [{"buffer": 0, "byteLength": len(thumbnail)}]
        binary = thumbnail
    path.write_bytes(glb(doc, binary))
    return path


def vrma(path: Path) -> Path:
    doc = {"asset": {"version": "2.0"},
           "extensions": {"VRMC_vrm_animation": {"specVersion": "1.0", "humanoid": {"humanBones": {}}}}}
    path.write_bytes(glb(doc))
    return path
