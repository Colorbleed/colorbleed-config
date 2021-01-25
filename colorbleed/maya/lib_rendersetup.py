from maya import cmds
import maya.api.OpenMaya as om
import pymel.core as pm

import maya.app.renderSetup.model.utils as utils
from maya.app.renderSetup.model import (
    override,
    selector,
    collection,
    renderLayer,
    renderSetup
)
from maya.app.renderSetup.model.override import (
    AbsOverride,
    RelOverride,
    UniqueOverride
)

ExactMatch = 0
ParentMatch = 1
ChildMatch = 2


def get_rendersetup_layer(layer):
    """Return render setup layer name.

    This also converts names from legacy renderLayer node name to render setup
    name.

    Note: `defaultRenderLayer` is not a renderSetupLayer node but it is however
          the valid layer name for Render Setup - so we return that as is.

    Example:
        >>> for legacy_layer in cmds.ls(type="renderLayer"):
        >>>    print get_rendersetup_layer(layer)

    Returns:
        str or None: Returns renderSetupLayer node name if `layer` is a valid
            layer name in legacy renderlayers or render setup layers.
            Returns None if the layer can't be found or Render Setup is
            currently disabled.


    """
    if layer == "defaultRenderLayer":
        # defaultRenderLayer doesn't have a `renderSetupLayer`
        return layer

    if not cmds.mayaHasRenderSetup():
        return None

    if cmds.objExists(layer) and cmds.nodeType(layer) == "renderSetupLayer":
        return layer

    # By default Render Setup renames the legacy renderlayer
    # to `rs_<layername>` but lets not rely on that as the
    # layer node can be renamed manually
    connections = cmds.listConnections(layer + ".message",
                                       type="renderSetupLayer",
                                       exactType=True,
                                       source=False,
                                       destination=True,
                                       plugs=True) or []
    return next((conn.split(".", 1)[0] for conn in connections
                 if conn.endswith(".legacyRenderLayer")), None)


def get_attr_in_layer(node_attr, layer):
    """Return attribute value in Render Setup layer.

    This will only work for attributes which can be
    retrieved with `maya.cmds.getAttr` and for which
    Relative and Absolute overrides are applicable.

    Examples:
        >>> get_attr_in_layer("defaultResolution.width", layer="layer1")
        >>> get_attr_in_layer("defaultRenderGlobals.startFrame", layer="layer")
        >>> get_attr_in_layer("transform.translate", layer="layer3")

    Args:
        attr (str): attribute name as 'node.attribute'
        layer (str): layer name

    Returns:
        object: attribute value in layer

    """

    def _layer_needs_update(layer):
        """Return whether layer needs updating."""
        # Use `getattr` as e.g. DefaultRenderLayer does not have the attribute
        return getattr(layer, "needsMembershipUpdate", False) or \
               getattr(layer, "needsApplyUpdate", False)

    def get_default_layer_value(node_attr_):
        """Return attribute value in defaultRenderLayer"""
        appliers = cmds.ls(cmds.listHistory(node_attr_,
                                            pruneDagObjects=True),
                           type="applyOverride")
        if appliers:
            node_attr_ = appliers[-1] + ".original"
        return pm.getAttr(node_attr_, asString=True)

    layer = get_rendersetup_layer(layer)
    rs = renderSetup.instance()
    current_layer = rs.getVisibleRenderLayer()
    if current_layer.name() == layer:

        # Ensure layer is up-to-date
        if _layer_needs_update(current_layer):
            try:
                rs.switchToLayer(current_layer)
            except RuntimeError as exc:
                # Some cases can cause errors on switching
                # the first time with Render Setup layers
                # e.g. different overrides to compounds
                # and its children plugs. So we just force
                # it another time. If it then still fails
                # we will let it error out.
                rs.switchToLayer(current_layer)

        return pm.getAttr(node_attr, asString=True)

    overrides = get_attr_overrides(node_attr, layer)
    default_layer_value = get_default_layer_value(node_attr)
    if not overrides:
        return default_layer_value

    value = default_layer_value
    for match, layer_override, index in overrides:
        if isinstance(layer_override, AbsOverride):
            # Absolute override
            value = pm.getAttr(layer_override.name() + ".attrValue")
            if match == ExactMatch:
                value = value
            if match == ParentMatch:
                value = value[index]
            if match == ChildMatch:
                value[index] = value

        elif isinstance(layer_override, RelOverride):
            # Relative override
            # Value = Original * Multiply + Offset
            multiply = pm.getAttr(layer_override.name() + ".multiply")
            offset = pm.getAttr(layer_override.name() + ".offset")

            if match == ExactMatch:
                value = value * multiply + offset
            if match == ParentMatch:
                value = value * multiply[index] + offset[index]
            if match == ChildMatch:
                value[index] = value[index] * multiply + offset

        else:
            raise TypeError("Unsupported override: %s" % layer_override)

    return value


def get_attr_overrides(node_attr, layer,
                       skip_disabled=True,
                       skip_local_render=True,
                       stop_at_absolute_override=True):
    """Return all Overrides applicable to the attribute.

    Overrides are returned as a 3-tuple:
        (Match, Override, Index)

    Match:
        This is any of ExactMatch, ParentMatch, ChildMatch
        and defines whether the override is exactly on the
        plug, on the parent or on a child plug.

    Override:
        This is the RenderSetup Override instance.

    Index:
        This is the Plug index under the parent or for
        the child that matches. The ExactMatch index will
        always be None. For ParentMatch the index is which
        index the plug is under the parent plug. For ChildMatch
        the index is which child index matches the plug.

    Args:
        node_attr (str): attribute name as 'node.attribute'
        layer (str): layer name
        skip_disabled (bool): exclude disabled overrides
        skip_local_render (bool): exclude overrides marked
            as local render.
        stop_at_absolute_override: exclude overrides prior
            to the last absolute override as they have
            no influence on the resulting value.

    Returns:
        list: Ordered Overrides in order of strength

    """

    def get_mplug_children(plug):
        """Return children MPlugs of compound MPlug"""
        children = []
        if plug.isCompound:
            for i in range(plug.numChildren()):
                children.append(plug.child(i))
        return children

    def get_mplug_names(mplug):
        """Return long and short name of MPlug"""
        l = mplug.partialName(useLongNames=True)
        s = mplug.partialName(useLongNames=False)
        return {l, s}

    def iter_override_targets(override):
        try:
            for target in override._targets():
                yield target
        except AssertionError:
            # Workaround: There is a bug where the private `_targets()` method
            #             fails on some attribute plugs. For example overrides
            #             to the defaultRenderGlobals.endFrame
            #             (Tested in Maya 2020.2)
            print("Workaround for %s" % override)
            from maya.app.renderSetup.common.utils import findPlug

            attr = override.attributeName()
            if isinstance(override, UniqueOverride):
                node = override.targetNodeName()
                yield findPlug(node, attr)
            else:
                nodes = override.parent().selector().nodes()
                for node in nodes:
                    if cmds.attributeQuery(attr, node=node, exists=True):
                        yield findPlug(node, attr)

    # Get the MPlug for the node.attr
    sel = om.MSelectionList()
    sel.add(node_attr)
    plug = sel.getPlug(0)

    layer = get_rendersetup_layer(layer)
    rs_layer = renderSetup.instance().getRenderLayer(layer)
    if rs_layer is None:
        # Renderlayer does not exist
        return

    # Get any parent or children plugs as we also
    # want to include them in the attribute match
    # for overrides
    parent = plug.parent() if plug.isChild else None
    parent_index = None
    if parent:
        parent_index = get_mplug_children(parent).index(plug)

    children = get_mplug_children(plug)

    # Create lookup for the attribute by both long
    # and short names
    attr_names = get_mplug_names(plug)
    for child in children:
        attr_names.update(get_mplug_names(child))
    if parent:
        attr_names.update(get_mplug_names(parent))

        # Get all overrides of the layer
    # And find those that are relevant to the attribute
    plug_overrides = []

    # Iterate over the overrides in reverse so we get the last
    # overrides first and can "break" whenever an absolute
    # override is reached
    layer_overrides = list(utils.getOverridesRecursive(rs_layer))
    for layer_override in reversed(layer_overrides):

        if skip_disabled and not layer_override.isEnabled():
            # Ignore disabled overrides
            continue

        if skip_local_render and layer_override.isLocalRender():
            continue

        # The targets list can be very large so we'll do
        # a quick filter by attribute name to detect whether
        # it matches the attribute name, or its parent or child
        if layer_override.attributeName() not in attr_names:
            continue

        override_match = None
        for override_plug in iter_override_targets(layer_override):

            override_match = None
            if plug == override_plug:
                override_match = (ExactMatch, layer_override, None)

            elif parent and override_plug == parent:
                override_match = (ParentMatch, layer_override, parent_index)

            elif children and override_plug in children:
                child_index = children.index(override_plug)
                override_match = (ChildMatch, layer_override, child_index)

            if override_match:
                plug_overrides.append(override_match)
                break

        if (
                override_match and
                stop_at_absolute_override and
                isinstance(layer_override, AbsOverride) and
                # When the override is only on a child plug then it doesn't
                # override the entire value so we not stop at this override
                not override_match[0] == ChildMatch
        ):
            # If override is absolute override, then BREAK out
            # of parent loop we don't need to look any further as
            # this is the absolute override
            break

    return reversed(plug_overrides)
