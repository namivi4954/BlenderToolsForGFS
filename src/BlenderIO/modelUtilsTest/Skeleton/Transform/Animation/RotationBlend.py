from mathutils import Quaternion, Euler
from .TransformFunc import TransformFunc


# Whether to apply the bone-axis-permutation conjugation as
# `P @ v @ P_inv` or the other way round, `P_inv @ v @ P`. Both are
# "reasonable" conjugation directions and only empirical testing in Blender
# can say which one actually matches this project's axis convention - if
# facial animations still land on the wrong axis/direction after the
# Issue #157 fix, flip this and re-test.
BLEND_PERMUTATION_INVERTED = True


def _permutation_quats(model_transforms):
    P     = model_transforms.bone_axis_permutation.quat
    P_inv = model_transforms.bone_axis_permutation.quat_inv
    if BLEND_PERMUTATION_INVERTED:
        P, P_inv = P_inv, P
    return P, P_inv


# Parent-relative -> Bind-pose-relative
def parent_to_bind_rotation_blend_quaternion(rotations, bone_transforms, model_transforms):
    ba_inv = bone_transforms.rotation.quat_inv
    ba     = bone_transforms.rotation.quat
    return [ba_inv @ Quaternion(v) @ ba for v in rotations]


# Parent-relative -> Bind-pose-relative
#
# GitHub issue #157 (https://github.com/Pherakki/BlenderToolsForGFS/issues/157):
# Blend Animation rotations are not proper rotations that should be composed
# with the bind pose via quaternion multiplication/conjugation. Per the game's
# actual blend equation, they are additive Euler-angle offsets that get summed
# directly onto the Base Animation's Euler rotation. Converting the raw delta
# quaternion to a Quaternion object and conjugating it by the bone's bind pose
# (as done for absolute/Base Animation rotations in `parent_to_bind_rotation`)
# silently reintroduces the wrong "quaternion multiplication" blend equation
# and produces incorrect results once combined with the Base Animation.
#
# Instead, remap the raw delta's axes into Blender's frame with the fixed
# bone-axis permutation (a signed permutation of X/Y/Z, see
# GFS_MODEL_TRANSFORMS in Globals.py) via a proper quaternion conjugation -
# NOT by decomposing to Euler angles first and permuting the three numbers,
# which silently assumes the composition order is unaffected by the
# permutation (it generally isn't; only single-axis rotations are order-
# independent, so that approach looks right for simple cases and wrong for
# compound ones). Conjugating the quaternion first and decomposing the
# *result* with mathutils' own `to_euler('XYZ')` is self-consistent for any
# permutation, since mathutils always finds the correct XYZ-order angles for
# whatever rotation it is given. The per-bone bind-pose orientation is
# deliberately *not* applied here, since it is a rotation conjugation and
# would reintroduce the same issue.
def parent_to_bind_rotation_blend_euler(rotations, bone_transforms, model_transforms):
    P, P_inv = _permutation_quats(model_transforms)
    out = []
    for v in rotations:
        q_blender = P @ Quaternion(v) @ P_inv
        out.append(q_blender.to_euler('XYZ'))
    return out


def parent_to_bind_rotation_blend_matrix3x3(rotations, bone_transforms, model_transforms):
    ba_inv = bone_transforms.rotation.matrix3x3_inv
    ba     = bone_transforms.rotation.matrix3x3
    return [ba_inv @ v @ ba for v in rotations]

def parent_to_bind_rotation_blend_matrix4x4(rotations, bone_transforms, model_transforms):
    ba_inv = bone_transforms.rotation.matrix4x4_inv
    ba     = bone_transforms.rotation.matrix4x4
    return [ba_inv @ v @ ba for v in rotations]


# NOTE: The default/`quat` variant is what is actually used by the importer
# (see `build_blend_fcurves` in Import/ImportAnimations.py). It is set to the
# Euler-based transform above to fix issue #157. The `matrix3x3`/`matrix4x4`
# variants are left pointing at the original quaternion-conjugation
# implementation, as they are not currently exercised by the Blend Animation
# import path.
parent_to_bind_rotation_blend = TransformFunc(parent_to_bind_rotation_blend_euler,
                                              matrix3x3=parent_to_bind_rotation_blend_matrix3x3,
                                              matrix4x4=parent_to_bind_rotation_blend_matrix4x4,
                                              quat     =parent_to_bind_rotation_blend_euler)


# Bind-pose-relative -> Parent-relative
#
# Exact inverse of `parent_to_bind_rotation_blend_euler` above, kept
# symmetric with it for Issue #157: `rotations` here are the raw Euler
# triples read back off the bone's `rotation_euler` fcurves for a Blend
# Animation action (see `get_action_data` in Export/ExportAnimations.py).
# Undo the bone-axis permutation first, then reconstruct the raw delta
# quaternion with the inverse of the decomposition used on import, so that
# a Blend Animation that was imported with the fixed importer round-trips
# back out unchanged.
def bind_to_parent_rotation_blend_euler(rotations, bone_transforms, model_transforms):
    P, P_inv = _permutation_quats(model_transforms)
    out = []
    for e in rotations:
        q_blender = Euler([e.x, e.y, e.z], 'XYZ').to_quaternion()
        out.append(P_inv @ q_blender @ P)
    return out


def bind_to_parent_rotation_blend_quaternion(rotations, bone_transforms, model_transforms):
    ba_inv = bone_transforms.rotation.quat_inv
    ba     = bone_transforms.rotation.quat
    return [ba @ Quaternion(v) @ ba_inv for v in rotations]


def bind_to_parent_rotation_blend_matrix3x3(rotations, bone_transforms, model_transforms):
    ba_inv = bone_transforms.rotation.matrix3x3_inv
    ba     = bone_transforms.rotation.matrix3x3
    return [ba @ v @ ba_inv for v in rotations]


def bind_to_parent_rotation_blend_matrix4x4(rotations, bone_transforms, model_transforms):
    ba_inv = bone_transforms.rotation.matrix4x4_inv
    ba     = bone_transforms.rotation.matrix4x4
    return [ba @ v @ ba_inv for v in rotations]


# NOTE: The default/`quat` variant is what is actually used by the exporter
# (see `get_action_data` in Export/ExportAnimations.py), set to the
# Euler-based inverse above to keep export symmetric with the Issue #157
# import fix. The `matrix3x3`/`matrix4x4` variants are left pointing at the
# original quaternion-conjugation implementation, as they are not currently
# exercised by the Blend Animation export path.
bind_to_parent_rotation_blend = TransformFunc(bind_to_parent_rotation_blend_euler,
                                              matrix3x3=bind_to_parent_rotation_blend_matrix3x3,
                                              matrix4x4=bind_to_parent_rotation_blend_matrix4x4,
                                              quat     =bind_to_parent_rotation_blend_euler)
