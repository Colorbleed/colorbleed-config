import re

from maya import cmds
import maya.api.OpenMaya as om2

import pyblish.api
import colorbleed.api
import colorbleed.maya.action
from colorbleed.lib import grouper
from colorbleed.plugin import contextplugin_should_run


def get_reference_edits(reference_node):
    """Get the raw edits from Reference Node

    This would contain what placeHolderList entry belongs to which node.

    Args:
        reference_node (str): Reference node name.

    """
    sel = om2.MSelectionList()
    sel.add(reference_node)
    dep_reference_node = sel.getDependNode(0)
    fn_reference_node = om2.MFnDependencyNode(dep_reference_node)
    plug = fn_reference_node.findPlug("edits", False)
    return plug.getSetAttrCmds(om2.MPlug.kAll, True)


def get_placeholder_input_name(placeholder_attr):
    """Get original input name for reference.placeHolderList[] attribute.

    Returns the input attribute that the placeHolderList index entry
    refers so, e.g. the missing "cube.translateX" output.

    Args:
        placeholder_attr (str): The placeholder attribute including
            the index and node name, e.g. reference.placeHolderList[0]

    Returns:
        str: The node.attribute that is the missing input.

    """
    reference_node = placeholder_attr.split(".", 1)[0]
    # Find the original plug from the reference edits
    missing_plug = None
    for edit in get_reference_edits(reference_node):
        if placeholder_attr in edit:
            edit = edit.strip()
            missing_plug = edit.split(" ")[3].strip('"')
            return missing_plug


def iter_renderlayer_missing_nodes(layer):
    """Yield all missing reference overrides for a renderlayer.

    This will yield all placeHolderList entries and its
    connections that will have Maya raise the following error:

        Error: Cannot switch from 'layer' to 'other_layer' because
        of an override to a missing node within a referenced scene.
        Reload the referenced scene if it's unloaded, clean up the
        referenced scene or remove corresponding reference edits if
        the node has been deleted in the referenced scene.

    The results are yielded as a tuple of two tuples:
        (
          (placeholder, adjustment_out_plug),
          (adjustment_out_value, adjustment_destination)
        )

    This allows to easily break the connections if you want to
    remove the faulty ones, for example:

    >> for connections in iter_renderlayer_missing_nodes(layer):
    >>     for connection in connections:
    >>         cmds.disconnectAttr(*connection)

    Yields:
        tuple: A tuple containing two tuples of connections.

    """

    # Get renderlayer adjustments
    connections = cmds.listConnections(layer + ".outAdjustments",
                                       destination=False,
                                       connections=True,
                                       plugs=True) or []
    for out_plug, placeholder in grouper(connections, 2):

        # Consider only connections to reference nodes
        node = placeholder.split(".", 1)[0]
        if not cmds.objectType(node, isAType="reference"):
            continue

        # Check whether it's indeed a missing override connected
        # to `.placeHolderList`, if not skip this connection..
        match = re.match(r".*\.placeHolderList\[([1-9]+)\]$", placeholder)
        if not match:
            continue

        # Original out connection
        out_value = out_plug.replace(".outPlug", ".outValue")
        destination = cmds.connectionInfo(
            out_value,
            destinationFromSource=True
        )[0]

        # placeholder = {reference}.placeHolderList[]
        # out_plug = {layer}.outAdjustments[].outPlug
        # out_value = {layer}.outAdjustments[].outValue
        # destination = {destination.attr}
        yield ((placeholder, out_plug),
               (out_value, destination))


class ValidateRenderlayersNoMissingOverrides(pyblish.api.ContextPlugin):
    """Validate renderlayers have no overrides to missing referenced nodes

    This will validate that all renderlayers have no overrides to missing nodes
    in referenced scenes.

    This can be resolved automatically with:
        Colorbleed > Shading
            > Fix Renderlayer Missing Referenced Nodes Overrides

    Note that this fix will remove the failed reference overrides from the
    reference edits by breaking the placeholder connections to the reference
    node.

    """

    label = "Renderlayers no missing overrides"
    order = pyblish.api.ValidatorOrder
    hosts = ["maya"]
    families = ["colorbleed.renderlayer"]

    def process(self, context):

        # Workaround bug pyblish-base#250
        if not contextplugin_should_run(self, context):
            return

        layers = cmds.ls(type="renderLayer")

        # Ignore referenced layers
        layers = [layer for layer in layers
                  if not cmds.referenceQuery(layer, isNodeReferenced=True)]

        invalid = []
        for layer in layers:

            for connections in iter_renderlayer_missing_nodes(layer):

                missing_input = get_placeholder_input_name(connections[0][0])
                output = connections[0][1]

                self.log.error("Override found to a missing node "
                               "in referenced scene for renderlayer '%s': "
                               "%s -> %s" % (layer, missing_input, output))

                invalid = True

        if invalid:
            raise RuntimeError("Renderlayer overrides found to missing "
                               "nodes within a referenced scene. Please "
                               "remove corresponding reference edits.")
