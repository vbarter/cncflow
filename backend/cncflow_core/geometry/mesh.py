"""Tessellate a CadQuery/OCP shape to GLB. No WASM, no second kernel."""
from __future__ import annotations

import json
import struct


def triangles_to_glb(positions, indices, normals=None) -> bytes:
    """positions: [(x,y,z), ...]; indices: [i0,i1,i2, ...]."""
    if not positions or not indices:
        raise ValueError("empty mesh")
    nvert = len(positions)
    pos = b"".join(struct.pack("<fff", float(p[0]), float(p[1]), float(p[2])) for p in positions)
    if normals is None:
        normals = _face_normals(positions, indices)
    nor = b"".join(struct.pack("<fff", float(n[0]), float(n[1]), float(n[2])) for n in normals)
    idx = b"".join(struct.pack("<I", int(i)) for i in indices)
    binary = pos + nor + idx
    if len(binary) % 4:
        binary += b"\x00" * (4 - len(binary) % 4)
    pos_len = nvert * 12
    nor_off = pos_len
    idx_off = pos_len + nvert * 12
    xmin = min(p[0] for p in positions)
    ymin = min(p[1] for p in positions)
    zmin = min(p[2] for p in positions)
    xmax = max(p[0] for p in positions)
    ymax = max(p[1] for p in positions)
    zmax = max(p[2] for p in positions)
    gltf = {
        "asset": {"version": "2.0", "generator": "cncflow-mesh"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2}]}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": pos_len, "target": 34962},
            {"buffer": 0, "byteOffset": nor_off, "byteLength": pos_len, "target": 34962},
            {"buffer": 0, "byteOffset": idx_off, "byteLength": len(indices) * 4, "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0, "componentType": 5126, "count": nvert, "type": "VEC3",
                "min": [xmin, ymin, zmin], "max": [xmax, ymax, zmax],
            },
            {"bufferView": 1, "componentType": 5126, "count": nvert, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5125, "count": len(indices), "type": "SCALAR"},
        ],
    }
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    if len(json_bytes) % 4:
        json_bytes += b" " * (4 - len(json_bytes) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(binary)
    header = struct.pack("<4sII", b"glTF", 2, total)
    json_chunk = struct.pack("<I4s", len(json_bytes), b"JSON") + json_bytes
    bin_chunk = struct.pack("<I4s", len(binary), b"BIN\x00") + binary
    return header + json_chunk + bin_chunk


def _face_normals(positions, indices):
    normals = [[0.0, 0.0, 0.0] for _ in positions]
    for i in range(0, len(indices), 3):
        a, b, c = indices[i], indices[i + 1], indices[i + 2]
        ax, ay, az = positions[a]
        bx, by, bz = positions[b]
        cx, cy, cz = positions[c]
        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = cx - ax, cy - ay, cz - az
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        for idx in (a, b, c):
            normals[idx][0] += nx
            normals[idx][1] += ny
            normals[idx][2] += nz
    out = []
    for nx, ny, nz in normals:
        mag = (nx * nx + ny * ny + nz * nz) ** 0.5
        if mag < 1e-12:
            out.append((0.0, 0.0, 1.0))
        else:
            out.append((nx / mag, ny / mag, nz / mag))
    return out


def _stl_triangles(data: bytes):
    if len(data) < 84:
        raise ValueError("stl too small")
    count = int.from_bytes(data[80:84], "little")
    positions, indices = [], []
    off = 84
    for _ in range(count):
        if off + 50 > len(data):
            break
        _n, x1, y1, z1, x2, y2, z2, x3, y3, z3, _attr = struct.unpack_from("<12fH", data, off)
        base = len(positions)
        positions.extend(((x1, y1, z1), (x2, y2, z2), (x3, y3, z3)))
        indices.extend((base, base + 1, base + 2))
        off += 50
    if not indices:
        raise ValueError("stl has no triangles")
    return positions, indices


def _tessellate_shape(shape, deflection=0.4):
    verts, faces = shape.tessellate(deflection)
    positions = []
    for v in verts:
        if hasattr(v, "x"):
            positions.append((float(v.x), float(v.y), float(v.z)))
        elif hasattr(v, "X") and callable(v.X):
            positions.append((float(v.X()), float(v.Y()), float(v.Z())))
        else:
            positions.append((float(v[0]), float(v[1]), float(v[2])))
    indices = []
    for tri in faces:
        if len(tri) >= 3:
            indices.extend((int(tri[0]), int(tri[1]), int(tri[2])))
    return positions, indices


def shape_to_glb(shape, deflection=0.4) -> bytes:
    try:
        from cadquery import exporters
        import os
        import tempfile
        from pathlib import Path as _P
        fd, path = tempfile.mkstemp(suffix=".stl")
        os.close(fd)
        try:
            exporters.export(shape, path)
            raw = _P(path).read_bytes()
        finally:
            os.unlink(path)
        return triangles_to_glb(*_stl_triangles(raw))
    except Exception:
        positions, indices = _tessellate_shape(shape, deflection)
        return triangles_to_glb(positions, indices)


def _cascadio_step_to_glb(path: str) -> bytes:
    import os
    import tempfile
    from pathlib import Path as _P
    import cascadio
    fd, out = tempfile.mkstemp(suffix=".glb")
    os.close(fd)
    try:
        cascadio.step_to_glb(input_path=str(path), output_path=out)
        data = _P(out).read_bytes()
        if data[:4] != b"glTF":
            raise ValueError("cascadio 未产出 GLB")
        return data
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass


def step_to_glb(path: str, deflection=0.4) -> bytes:
    """Prefer cascadio (OCCT RWGltf). Fall back to live CadQuery tessellation."""
    try:
        return _cascadio_step_to_glb(path)
    except Exception:
        pass
    import cadquery as cq
    imported = cq.importers.importStep(path)
    values = imported.vals()
    if not values:
        raise ValueError("STEP中没有可解析的形状")
    compound = cq.Compound.makeCompound(values) if len(values) > 1 else values[0]
    return shape_to_glb(compound, deflection)
