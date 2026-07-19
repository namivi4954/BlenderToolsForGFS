import array
import math

from mathutils import Vector

from ...API.Version import bpy_at_least


# Blender's native custom-normals code (mesh_normals_corner_custom_set / mesh_set_custom_normals)
# is not defensive against malformed input: NaN, infinite, or zero-length normal vectors can lead
# to an EXCEPTION_ACCESS_VIOLATION crash deep in blender.exe rather than a catchable Python
# exception. Imported files (especially reverse-engineered/dumped game models) can and do contain
# corrupt per-vertex normal data that isn't caught anywhere upstream, so we sanitize every normal
# here - right before it reaches the native API - as a last line of defense.
def _sanitize_normal(n, fallback=(0.0, 0.0, 1.0)):
    try:
        x, y, z = float(n[0]), float(n[1]), float(n[2])
    except (TypeError, ValueError, IndexError):
        return fallback

    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
        return fallback

    length_sq = x * x + y * y + z * z
    if length_sq < 1e-12:
        return fallback

    return (x, y, z)


def _sanitize_normals(bpy_mesh, normals):
    n_loops = len(bpy_mesh.loops)
    normals = list(normals)

    if len(normals) != n_loops:
        # A count mismatch here means something upstream produced the wrong amount of loop data
        # for this mesh. Passing a mismatched-length array into normals_split_custom_set is
        # exactly the kind of thing that crashes Blender natively, so refuse to do it and fall
        # back to Blender's auto-generated normals instead of risking a hard crash.
        return None

    return [_sanitize_normal(n) for n in normals]


def _has_degenerate_geometry(bpy_mesh, area_epsilon=1e-10):
    # Before it can apply a custom normal to a corner, Blender's native
    # normals_split_custom_set computes a per-corner "normal space" from the surrounding face
    # geometry (edge directions/angles). For a zero-area face - e.g. a triangle where vertex
    # merging has collapsed two of its three corners onto the same position, which
    # "merge_vertices" policy can produce on meshes with duplicate/overlapping source vertices -
    # that computation degenerates, and Blender does not guard against it: it crashes natively
    # (EXCEPTION_ACCESS_VIOLATION) regardless of what normal values are supplied. Detect that
    # condition here so we can skip custom normal assignment for the mesh entirely rather than
    # crash Blender outright.
    for poly in bpy_mesh.polygons:
        if poly.area <= area_epsilon:
            return True
    return False


if bpy_at_least(4, 1, 0):
    def create_loop_normals(bpy_mesh, normals):
        bpy_mesh.polygons.foreach_set("use_smooth", [True] * len(bpy_mesh.polygons))

        safe_normals = _sanitize_normals(bpy_mesh, normals)
        if safe_normals is not None and not _has_degenerate_geometry(bpy_mesh):
            bpy_mesh.normals_split_custom_set([Vector(n) for n in safe_normals])

        bpy_mesh.validate(clean_customdata=False)
        bpy_mesh.update()
else:
    def create_loop_normals(bpy_mesh, normals):
        """
        Loads per-loop normal vectors into a mesh.
        
        Works thanks to this stackexchange answer https://blender.stackexchange.com/a/75957,
        which a few of these comments below are also taken from.
        """
        safe_normals = _sanitize_normals(bpy_mesh, normals)
        if safe_normals is None or _has_degenerate_geometry(bpy_mesh):
            bpy_mesh.polygons.foreach_set("use_smooth", [True] * len(bpy_mesh.polygons))
            bpy_mesh.use_auto_smooth = True
            return

        bpy_mesh.create_normals_split()
        for face in bpy_mesh.polygons:
            face.use_smooth = True  # loop normals have effect only if smooth shading ?
    
        # Set loop normals
        loop_normals = [Vector(normal) for normal in safe_normals]
        bpy_mesh.loops.foreach_set("normal", [subitem for item in loop_normals for subitem in item])
    
        bpy_mesh.validate(clean_customdata=False)  # important to not remove loop normals here!
        bpy_mesh.update()
    
        clnors = array.array('f', [0.0] * (len(bpy_mesh.loops) * 3))
        bpy_mesh.loops.foreach_get("normal", clnors)
    
        bpy_mesh.polygons.foreach_set("use_smooth", [True] * len(bpy_mesh.polygons))
        # This line is pretty smart (came from the stackoverflow answer)
        # 1. Creates three copies of the same iterator over clnors
        # 2. Splats those three copies into a zip
        # 3. Each iteration of the zip now calls the iterator three times, meaning that three consecutive elements
        #    are popped off
        # 4. Turn that triplet into a tuple
        # In this way, a flat list is iterated over in triplets without wasting memory by copying the whole list
        bpy_mesh.normals_split_custom_set(tuple(zip(*(iter(clnors),) * 3)))
    
        bpy_mesh.use_auto_smooth = True


def create_uv_map(bpy_mesh, name, uvs):
    uv_layer = bpy_mesh.uv_layers.new(name=name, do_init=True)
    for loop_idx, (loop, (u, v)) in enumerate(zip(bpy_mesh.loops, uvs)):
        uv_layer.data[loop_idx].uv = (u, v)



if bpy_at_least(3, 2, 0):
    def create_color_map(bpy_mesh, name, color_data, datatype):
        if datatype == "FLOAT":
            ca = bpy_mesh.color_attributes.new(name=name, type="FLOAT_COLOR", domain="CORNER")
            for loop_idx, loop in enumerate(bpy_mesh.loops):
                ca.data[loop_idx].color = color_data[loop_idx]
        elif datatype == "BYTE":
            ca = bpy_mesh.color_attributes.new(name=name, type="BYTE_COLOR", domain="CORNER")
            for loop_idx, loop in enumerate(bpy_mesh.loops):
                ca.data[loop_idx].color = [c/255 for c in color_data[loop_idx]]
        else:
            raise ValueError(f"Invalid datatype '{datatype}': allowed values are 'FLOAT' and 'BYTE'")
else:
    def create_color_map(bpy_mesh, name, color_data, datatype):
        vc = bpy_mesh.vertex_colors.new(name=name)
        if datatype == "FLOAT":
            for loop_idx, loop in enumerate(bpy_mesh.loops):
                vc.data[loop_idx].color = color_data[loop_idx]
        elif datatype == "BYTE":
            for loop_idx, loop in enumerate(bpy_mesh.loops):
                vc.data[loop_idx].color = [c/255 for c in color_data[loop_idx]]
        else:
            raise ValueError(f"Invalid datatype '{datatype}': allowed values are 'FLOAT' and 'BYTE'")
            
