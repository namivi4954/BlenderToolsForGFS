##############################################################################
# Blender Action API compatibility helpers
##############################################################################
# Blender 4.4 introduced "Slotted Actions": F-Curves and Channel Groups are
# no longer stored directly on the Action, but on a Channelbag that belongs
# to a Slot (an Action can now hold the animation of several different
# data-blocks at once). For backwards compatibility, Blender 4.4 kept
# `action.fcurves` / `action.groups` / `action.id_root` around as proxies
# that transparently operated on the first slot's channelbag.
#
# Blender 5.0 removed that compatibility shim entirely: accessing
# `action.fcurves` or `action.groups` now raises
#   AttributeError: 'Action' object has no attribute 'fcurves'
#
# The helpers below always talk to the Channelbag/Slot API directly, which
# has existed since Blender 4.4, so the exact same code path works
# unchanged on both 4.4 and 5.0+. Versions older than 4.4 (which have no
# concept of Slots at all) are also supported by falling back to using the
# legacy Action object itself wherever a Channelbag is expected, since a
# legacy Action already provides `.fcurves`/`.groups` directly.
##############################################################################


def _is_slotted_action(action):
    return hasattr(action, "slots")


def get_action_slot(action, id_data, create=True):
    """
    Finds the ActionSlot on `action` that is intended for `id_data`
    (matched by ID type), creating one if it doesn't exist yet and
    `create` is True. Returns None on Blender versions that predate
    Slotted Actions (< 4.4), since there is no such concept there.
    """
    if not _is_slotted_action(action):
        return None

    id_type = id_data.id_type
    for slot in action.slots:
        if slot.target_id_type == id_type:
            return slot

    if not create:
        return None

    return action.slots.new(id_type=id_type, name=id_data.name)


def get_channelbag(action, id_data, create=True):
    """
    Returns the object exposing `.fcurves` / `.groups` for `id_data` within
    `action`, creating the Slot/Layer/Strip/Channelbag chain as necessary.

    On Blender < 4.4, this is simply the Action itself. On Blender 4.4+,
    this walks down to the Channelbag belonging to the Slot matching
    `id_data`'s ID type, creating the Layer/Strip/Slot/Channelbag along the
    way if they don't exist yet.
    """
    if not _is_slotted_action(action):
        return action

    slot = get_action_slot(action, id_data, create=create)
    if slot is None:
        return None

    if len(action.layers):
        layer = action.layers[0]
    elif create:
        layer = action.layers.new("Layer")
    else:
        return None

    if len(layer.strips):
        strip = layer.strips[0]
    elif create:
        strip = layer.strips.new(type='KEYFRAME')
    else:
        return None

    return strip.channelbag(slot, ensure=create)


def assign_action(anim_data, action, id_data=None):
    """
    Assigns `action` as the active Action on `anim_data` (an
    AnimData/PropertyGroup with an `.action` slot, e.g.
    `some_object.animation_data`), also making sure a matching Action Slot
    is selected.

    A plain `anim_data.action = action` assignment does not reliably select
    a Slot on Blender 4.4+ (Slotted Actions) - without doing so explicitly,
    the assignment can silently leave the target un-animated.
    """
    anim_data.action = action
    if action is None or not _is_slotted_action(action):
        return

    slot = None
    if id_data is not None:
        slot = get_action_slot(action, id_data, create=False)
    if slot is None:
        suitable = getattr(anim_data, "action_suitable_slots", None)
        if suitable and len(suitable):
            slot = suitable[0]
    if slot is not None:
        anim_data.action_slot = slot
