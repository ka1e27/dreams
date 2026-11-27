"""Build media/boat-v3.glb for the Boat page's 3D boat (boat-explorer.js) from a STEP export of the
team's SolidWorks part (File > Save As > STEP; show every body first, hidden bodies are left out).

    pip install cadquery-ocp
    python -I tools/step2glb.py "Boat.V2.1.STEP" media/boat-v3.glb

The STEP is Z up with +y toward the bow, in mm. The GLB is what boat-explorer.js reads: one node per part
under a root "Boat", metres, Y up, +x starboard, -z toward the bow, and extras {id, kind, size_mm,
volume_l, bodies} on each part. Parts are found by their SolidWorks body names (PARTS below); a body the
list doesn't name is reported and left out. Faces keep their own vertices, so edges stay sharp.
"""

import json
import re
import struct
import sys

import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Solid

LIN_DEFL_MM, ANG_DEFL_RAD = 0.3, 0.35

# part id, node name, kind (colour in boat-explorer.js), required body names, optional body names
PARTS: list[tuple[str, str, str, list[str], list[str]]] = [
    ("bridge", "Bridge", "bridge",
     ["Split6[1]", "Split6[2]", "Split6[4]", "Split6[5]", "Split6[6]"], ["Split6[3]"]),
    ("name", "“Dr. Eams” lettering", "name", [f"Boss-Extrude6[{i}]" for i in range(1, 8)], []),
    ("hull-port", "Port hull", "hull", ["Combine1"], []),
    ("deck-port", "Port deck plate", "deck", ["Cut-Extrude10"], []),
    ("hull-stbd", "Starboard hull", "hull", ["Fillet1"], []),
    ("deck-stbd", "Starboard deck plate", "deck", ["Cut-Extrude9"], []),
    ("truss-front", "Front truss", "truss", ["Mirror7"], []),
    ("truss-back", "Back truss", "truss", ["Ø4.5 (4.5) Diameter Hole1"], []),
    ("brackets", "Hull brackets", "bracket", ["Cut-Extrude12[1]", "Cut-Extrude12[2]"], []),
]
COLORS = {"bridge": "#FFC0C0", "name": "#E4E4E4", "hull": "#C00000", "deck": "#FFFFFF",
          "truss": "#8C939B", "bracket": "#A9B0B7"}
ROUGH = {"bridge": 0.55, "name": 0.35, "hull": 0.55, "deck": 0.45, "truss": 0.4, "bracket": 0.4}
METAL = {"truss": 0.6, "bracket": 0.6}


def body_names(path: str) -> list[tuple[str, int]]:
    """(name, face count) of each MANIFOLD_SOLID_BREP, in the order the shape representation lists them."""
    txt = open(path, encoding="latin-1").read()
    data = txt[txt.index("DATA;"):]
    ents = {int(m.group(1)): (m.group(2), m.group(3))
            for m in re.finditer(r"#(\d+)\s*=\s*([A-Z_0-9]+)\s*\((.*?)\)\s*;", data, re.S)}
    rep = next(v for v in ents.values() if v[0] == "ADVANCED_BREP_SHAPE_REPRESENTATION")
    out = []
    for i in (int(k) for k in re.findall(r"#(\d+)", rep[1])[:-1]):  # the last ref is the context
        kind, args = ents[i]
        if kind != "MANIFOLD_SOLID_BREP":
            continue
        name = re.match(r"\s*'(.*?)'", args, re.S).group(1)
        name = re.sub(r"\\X2\\([0-9A-Fa-f]+)\\X0\\",
                      lambda m: "".join(chr(int(m.group(1)[k:k + 4], 16)) for k in range(0, len(m.group(1)), 4)),
                      name)
        shell = int(re.findall(r"#(\d+)", args)[0])
        out.append((name, len(re.findall(r"#\d+", ents[shell][1]))))
    return out


def count_faces(shape: TopoDS_Solid) -> int:
    n, ex = 0, TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        n += 1
        ex.Next()
    return n


def load_bodies(path: str) -> dict[str, TopoDS_Solid]:
    """SolidWorks body name -> solid. Names and solids are matched in order and checked by face count."""
    r = STEPControl_Reader()
    if r.ReadFile(path) != IFSelect_RetDone:
        raise SystemExit(f"can't read {path}")
    r.TransferRoots()
    solids, ex = [], TopExp_Explorer(r.OneShape(), TopAbs_SOLID)
    while ex.More():
        solids.append(TopoDS.Solid(ex.Current()))
        ex.Next()
    names = body_names(path)
    if len(names) != len(solids) or any(nf != count_faces(s) for (_, nf), s in zip(names, solids)):
        raise SystemExit("body names and solids don't line up")
    return {nm: s for (nm, _), s in zip(names, solids)}


def tessellate(solid: TopoDS_Solid) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Points (mm), normals and triangles; each face keeps its own vertices, smooth within the face."""
    BRepMesh_IncrementalMesh(solid, LIN_DEFL_MM, False, ANG_DEFL_RAD, True)
    pts_all, nrm_all, tri_all, base = [], [], [], 0
    ex = TopExp_Explorer(solid, TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face(ex.Current())
        ex.Next()
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            continue
        tr = loc.Transformation()
        pts = np.array([[p.X(), p.Y(), p.Z()]
                        for p in (tri.Node(i).Transformed(tr) for i in range(1, tri.NbNodes() + 1))])
        idx = np.array([[t.Value(1), t.Value(2), t.Value(3)]
                        for t in (tri.Triangle(i) for i in range(1, tri.NbTriangles() + 1))]) - 1
        if face.Orientation() == TopAbs_REVERSED:
            idx = idx[:, [0, 2, 1]]
        fn = np.cross(pts[idx[:, 1]] - pts[idx[:, 0]], pts[idx[:, 2]] - pts[idx[:, 0]])
        vn = np.zeros_like(pts)
        for k in range(3):
            np.add.at(vn, idx[:, k], fn)
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
        pts_all.append(pts)
        nrm_all.append(vn)
        tri_all.append(idx + base)
        base += len(pts)
    return np.vstack(pts_all), np.vstack(nrm_all), np.vstack(tri_all)


def to_glb_axes(v: np.ndarray) -> np.ndarray:
    """STEP (x, y, z), Z up, +y bow -> glTF (x, z, -y), Y up, -z bow."""
    return np.c_[v[:, 0], v[:, 2], -v[:, 1]]


def srgb_to_linear(c: int) -> float:
    c_ = c / 255.0
    return c_ / 12.92 if c_ <= 0.04045 else ((c_ + 0.055) / 1.055) ** 2.4


def build(step: str, out: str) -> None:
    solids = load_bodies(step)
    named = {b for p in PARTS for b in p[3] + p[4]}
    missing = [b for p in PARTS for b in p[3] if b not in solids]
    if missing:
        raise SystemExit(f"bodies missing from the STEP: {missing}")
    for b in solids:
        if b not in named:
            print("left out (not in PARTS):", b)
    kinds = list(dict.fromkeys(p[2] for p in PARTS))
    materials = []
    for k in kinds:
        h = COLORS[k].lstrip("#")
        rgb = [round(srgb_to_linear(int(h[i:i + 2], 16)), 5) for i in (0, 2, 4)]
        materials.append({"name": f"{k} {COLORS[k]}", "pbrMetallicRoughness": {
            "baseColorFactor": rgb + [1.0], "metallicFactor": METAL.get(k, 0.0), "roughnessFactor": ROUGH[k]}})
    blob = bytearray()
    views, accessors, meshes, nodes = [], [], [], []

    def add_view(data: bytes, target: int) -> int:
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": target})
        blob.extend(data)
        return len(views) - 1

    for pid, title, kind, required, optional in PARTS:
        names = required + [b for b in optional if b in solids]
        pts_l, nrm_l, tri_l, base, vol = [], [], [], 0, 0.0
        for nm in names:
            p, n, t = tessellate(solids[nm])
            pts_l.append(p)
            nrm_l.append(n)
            tri_l.append(t + base)
            base += len(p)
            g = GProp_GProps()
            BRepGProp.VolumeProperties_s(solids[nm], g)
            vol += g.Mass()
        p_mm = np.vstack(pts_l)
        pos = (to_glb_axes(p_mm) / 1000.0).astype(np.float32)
        nrm = to_glb_axes(np.vstack(nrm_l)).astype(np.float32)
        big = len(pos) > 65535
        idx = np.vstack(tri_l).ravel().astype(np.uint32 if big else np.uint16)
        pv, nv, iv = add_view(pos.tobytes(), 34962), add_view(nrm.tobytes(), 34962), add_view(idx.tobytes(), 34963)
        a0 = len(accessors)
        accessors += [
            {"bufferView": pv, "componentType": 5126, "count": len(pos), "type": "VEC3",
             "min": pos.min(0).tolist(), "max": pos.max(0).tolist()},
            {"bufferView": nv, "componentType": 5126, "count": len(nrm), "type": "VEC3"},
            {"bufferView": iv, "componentType": 5125 if big else 5123, "count": len(idx), "type": "SCALAR"},
        ]
        meshes.append({"name": title, "primitives": [{"attributes": {"POSITION": a0, "NORMAL": a0 + 1},
                                                      "indices": a0 + 2, "material": kinds.index(kind)}]})
        ext = p_mm.max(0) - p_mm.min(0)
        size = {"length": round(float(ext[1]), 1), "beam": round(float(ext[0]), 1), "height": round(float(ext[2]), 1)}
        nodes.append({"name": title, "mesh": len(meshes) - 1, "extras": {
            "id": pid, "kind": kind, "size_mm": size, "volume_l": round(vol / 1e6, 3), "bodies": names}})
        print(f"{pid:12s} {len(pos):6d} vertices {len(idx) // 3:6d} triangles  {size}  {vol / 1e6:.3f} L")
    gltf = {
        "asset": {"version": "2.0", "generator": "D.R.E.A.M.S step2glb (STEP export, OpenCASCADE tessellation)"},
        "scene": 0,
        "scenes": [{"name": "Boat.V2.1", "nodes": [0]}],
        "nodes": [{"name": "Boat", "children": list(range(1, len(nodes) + 1)),
                   "extras": {"source": "Boat.V2.1.SLDPRT (STEP export)", "units": "m"}}] + nodes,
        "meshes": meshes, "materials": materials, "accessors": accessors, "bufferViews": views,
        "buffers": [{"byteLength": len(blob)}],
    }
    js = json.dumps(gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    js += b" " * (-len(js) % 4)
    blob.extend(b"\0" * (-len(blob) % 4))
    with open(out, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, 28 + len(js) + len(blob)))
        fh.write(struct.pack("<I4s", len(js), b"JSON") + js)
        fh.write(struct.pack("<I4s", len(blob), b"BIN\0") + bytes(blob))
    print(f"wrote {out}: {(28 + len(js) + len(blob)) / 1e6:.2f} MB")


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
