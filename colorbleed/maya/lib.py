"""Standalone helper functions"""

import re
import os
import uuid

import bson
import json
import logging
import contextlib
from collections import OrderedDict, defaultdict

from maya import cmds, mel
import maya.api.OpenMaya as om

from avalon import api, maya, io, pipeline
from avalon.vendor.six import string_types
import avalon.maya.lib

from colorbleed import lib


log = logging.getLogger(__name__)

ATTRIBUTE_DICT = {"int": {"attributeType": "long"},
                  "str": {"dataType": "string"},
                  "unicode": {"dataType": "string"},
                  "float": {"attributeType": "double"},
                  "bool": {"attributeType": "bool"}}


RENDER_ATTRS = {"vray":
                    {
                        "node": "vraySettings",
                        "prefix": "fileNamePrefix",
                        "padding": "fileNamePadding",
                        "ext": "imageFormatStr"
                    },
                "default":
                    {
                        "node": "defaultRenderGlobals",
                        "prefix": "imageFilePrefix",
                        "padding": "extensionPadding"
                    }
                }


DEFAULT_MATRIX = [1.0, 0.0, 0.0, 0.0,
                  0.0, 1.0, 0.0, 0.0,
                  0.0, 0.0, 1.0, 0.0,
                  0.0, 0.0, 0.0, 1.0]

# The maya alembic export types
_alembic_options = {
    "startFrame": float,
    "endFrame": float,
    "frameRange": str,  # "start end"; overrides startFrame & endFrame
    "eulerFilter": bool,
    "frameRelativeSample": float,
    "noNormals": bool,
    "renderableOnly": bool,
    "step": float,
    "stripNamespaces": bool,
    "uvWrite": bool,
    "wholeFrameGeo": bool,
    "worldSpace": bool,
    "writeVisibility": bool,
    "writeColorSets": bool,
    "writeFaceSets": bool,
    "writeCreases": bool,  # Maya 2015 Ext1+
    "writeUVSets": bool,   # Maya 2017+
    "dataFormat": str,
    "root": (list, tuple),
    "attr": (list, tuple),
    "attrPrefix": (list, tuple),
    "userAttr": (list, tuple),
    "melPerFrameCallback": str,
    "melPostJobCallback": str,
    "pythonPerFrameCallback": str,
    "pythonPostJobCallback": str,
    "selection": bool
}

INT_FPS = {15, 24, 25, 30, 48, 50, 60, 44100, 48000}
FLOAT_FPS = {23.976, 29.97, 47.952, 59.94}


def _get_mel_global(name):
    """Return the value of a mel global variable"""
    return mel.eval("$%s = $%s;" % (name, name))


def matrix_equals(a, b, tolerance=1e-10):
    """
    Compares two matrices with an imperfection tolerance

    Args:
        a (list, tuple): the matrix to check
        b (list, tuple): the matrix to check against
        tolerance (float): the precision of the differences

    Returns:
        bool : True or False

    """
    if not all(abs(x - y) < tolerance for x, y in zip(a, b)):
        return False
    return True


def collect_animation_data():
    """Get the basic animation data

    Returns:
        OrderedDict

    """

    # get scene values as defaults
    start = cmds.playbackOptions(query=True, animationStartTime=True)
    end = cmds.playbackOptions(query=True, animationEndTime=True)

    # build attributes
    data = OrderedDict()
    data["startFrame"] = start
    data["endFrame"] = end
    data["handles"] = 1
    data["step"] = 1.0

    return data


@contextlib.contextmanager
def attribute_values(attr_values):
    """Remaps node attributes to values during context.

    Arguments:
        attr_values (dict): Dictionary with (attr, value)

    """

    original = [(attr, cmds.getAttr(attr)) for attr in attr_values]
    try:
        for attr, value in attr_values.items():
            if isinstance(value, string_types):
                cmds.setAttr(attr, value, type="string")
            else:
                cmds.setAttr(attr, value)
        yield
    finally:
        for attr, value in original:
            if isinstance(value, string_types):
                cmds.setAttr(attr, value, type="string")
            elif value is None and cmds.getAttr(attr, type=True) == "string":
                # In some cases the maya.cmds.getAttr command returns None
                # for string attributes but this value cannot assigned.
                # Note: After setting it once to "" it will then return ""
                #       instead of None. So this would only happen once.
                cmds.setAttr(attr, "", type="string")
            else:
                cmds.setAttr(attr, value)


@contextlib.contextmanager
def keytangent_default(in_tangent_type='auto',
                       out_tangent_type='auto'):
    """Set the default keyTangent for new keys during this context"""

    original_itt = cmds.keyTangent(query=True, g=True, itt=True)[0]
    original_ott = cmds.keyTangent(query=True, g=True, ott=True)[0]
    cmds.keyTangent(g=True, itt=in_tangent_type)
    cmds.keyTangent(g=True, ott=out_tangent_type)
    try:
        yield
    finally:
        cmds.keyTangent(g=True, itt=original_itt)
        cmds.keyTangent(g=True, ott=original_ott)


@contextlib.contextmanager
def undo_chunk():
    """Open a undo chunk during context."""

    try:
        cmds.undoInfo(openChunk=True)
        yield
    finally:
        cmds.undoInfo(closeChunk=True)


@contextlib.contextmanager
def renderlayer(layer):
    """Set the renderlayer during the context"""

    original = cmds.editRenderLayerGlobals(query=True, currentRenderLayer=True)

    try:
        cmds.editRenderLayerGlobals(currentRenderLayer=layer)
        yield
    finally:
        cmds.editRenderLayerGlobals(currentRenderLayer=original)


@contextlib.contextmanager
def evaluation(mode="off"):
    """Set the evaluation manager during context.

    Arguments:
        mode (str): The mode to apply during context.
            "off": The standard DG evaluation (stable)
            "serial": A serial DG evaluation
            "parallel": The Maya 2016+ parallel evaluation

    """

    original = cmds.evaluationManager(query=True, mode=1)[0]
    try:
        cmds.evaluationManager(mode=mode)
        yield
    finally:
        cmds.evaluationManager(mode=original)


@contextlib.contextmanager
def empty_sets(sets, force=False):
    """Remove all members of the sets during the context"""

    assert isinstance(sets, (list, tuple))

    original = dict()
    original_connections = []

    # Store original state
    for obj_set in sets:
        members = cmds.sets(obj_set, query=True)
        original[obj_set] = members

    try:
        for obj_set in sets:
            cmds.sets(clear=obj_set)
            if force:
                # Break all connections if force is enabled, this way we
                # prevent Maya from exporting any reference nodes which are
                # connected with placeHolder[x] attributes
                plug = "%s.dagSetMembers" % obj_set
                connections = cmds.listConnections(plug,
                                                   source=True,
                                                   destination=False,
                                                   plugs=True,
                                                   connections=True) or []
                original_connections.extend(connections)
                for dest, src in lib.pairwise(connections):
                    cmds.disconnectAttr(src, dest)
        yield
    finally:

        for dest, src in lib.pairwise(original_connections):
            cmds.connectAttr(src, dest)

        # Restore original members
        for origin_set, members in original.iteritems():
            cmds.sets(members, forceElement=origin_set)


@contextlib.contextmanager
def renderlayer(layer):
    """Set the renderlayer during the context

    Arguments:
        layer (str): Name of layer to switch to.

    """

    original = cmds.editRenderLayerGlobals(query=True,
                                           currentRenderLayer=True)

    try:
        cmds.editRenderLayerGlobals(currentRenderLayer=layer)
        yield
    finally:
        cmds.editRenderLayerGlobals(currentRenderLayer=original)


class delete_after(object):
    """Context Manager that will delete collected nodes after exit.

    This allows to ensure the nodes added to the context are deleted
    afterwards. This is useful if you want to ensure nodes are deleted
    even if an error is raised.

    Examples:
        with delete_after() as delete_bin:
            cube = maya.cmds.polyCube()
            delete_bin.extend(cube)
            # cube exists
        # cube deleted

    """

    def __init__(self, nodes=None):

        self._nodes = list()

        if nodes:
            self.extend(nodes)

    def append(self, node):
        self._nodes.append(node)

    def extend(self, nodes):
        self._nodes.extend(nodes)

    def __iter__(self):
        return iter(self._nodes)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if self._nodes:
            cmds.delete(self._nodes)


@contextlib.contextmanager
def no_undo(flush=False):
    """Disable the undo queue during the context

    Arguments:
        flush (bool): When True the undo queue will be emptied when returning
            from the context losing all undo history. Defaults to False.

    """
    original = cmds.undoInfo(query=True, state=True)
    keyword = 'state' if flush else 'stateWithoutFlush'

    try:
        cmds.undoInfo(**{keyword: False})
        yield
    finally:
        cmds.undoInfo(**{keyword: original})


def get_shader_assignments_from_shapes(shapes, components=True):
    """Return the shape assignment per related shading engines.

    Returns a dictionary where the keys are shadingGroups and the values are
    lists of assigned shapes or shape-components.

    Since `maya.cmds.sets` returns shader members on the shapes as components
    on the transform we correct that in this method too.

    For the 'shapes' this will return a dictionary like:
        {
            "shadingEngineX": ["nodeX", "nodeY"],
            "shadingEngineY": ["nodeA", "nodeB"]
        }

    Args:
        shapes (list): The shapes to collect the assignments for.
        components (bool): Whether to include the component assignments.

    Returns:
        dict: The {shadingEngine: shapes} relationships

    """

    shapes = cmds.ls(shapes,
                     long=True,
                     shapes=True,
                     objectsOnly=True)
    if not shapes:
        return {}

    # Collect shading engines and their shapes
    assignments = defaultdict(list)
    for shape in shapes:

        # Get unique shading groups for the shape
        shading_groups = cmds.listConnections(shape,
                                              source=False,
                                              destination=True,
                                              plugs=False,
                                              connections=False,
                                              type="shadingEngine") or []
        shading_groups = list(set(shading_groups))
        for shading_group in shading_groups:
            assignments[shading_group].append(shape)

    if components:
        # Note: Components returned from maya.cmds.sets are "listed" as if
        # being assigned to the transform like: pCube1.f[0] as opposed
        # to pCubeShape1.f[0] so we correct that here too.

        # Build a mapping from parent to shapes to include in lookup.
        transforms = {shape.rsplit("|", 1)[0]: shape for shape in shapes}
        lookup = set(shapes + transforms.keys())

        component_assignments = defaultdict(list)
        for shading_group in assignments.keys():
            members = cmds.ls(cmds.sets(shading_group, query=True), long=True)
            for member in members:

                node = member.split(".", 1)[0]
                if node not in lookup:
                    continue

                # Component
                if "." in member:

                    # Fix transform to shape as shaders are assigned to shapes
                    if node in transforms:
                        shape = transforms[node]
                        component = member.split(".", 1)[1]
                        member = "{0}.{1}".format(shape, component)

                component_assignments[shading_group].append(member)
        assignments = component_assignments

    return dict(assignments)


@contextlib.contextmanager
def shader(nodes, shadingEngine="initialShadingGroup"):
    """Assign a shader to nodes during the context"""

    shapes = cmds.ls(nodes, dag=1, objectsOnly=1, shapes=1, long=1)
    original = get_shader_assignments_from_shapes(shapes)

    try:
        # Assign override shader
        if shapes:
            cmds.sets(shapes, edit=True, forceElement=shadingEngine)
        yield
    finally:

        # Assign original shaders
        for sg, members in original.items():
            if members:
                cmds.sets(members, edit=True, forceElement=sg)


@contextlib.contextmanager
def displaySmoothness(nodes,
                      divisionsU=0,
                      divisionsV=0,
                      pointsWire=4,
                      pointsShaded=1,
                      polygonObject=1):
    """Set the displaySmoothness during the context"""

    # Ensure only non-intermediate shapes
    nodes = cmds.ls(nodes,
                    dag=1,
                    shapes=1,
                    long=1,
                    noIntermediate=True)

    def parse(node):
        """Parse the current state of a node"""
        state = {}
        for key in ["divisionsU",
                    "divisionsV",
                    "pointsWire",
                    "pointsShaded",
                    "polygonObject"]:
            value = cmds.displaySmoothness(node, query=1, **{key: True})
            if value is not None:
                state[key] = value[0]
        return state

    originals = dict((node, parse(node)) for node in nodes)

    try:
        # Apply current state
        cmds.displaySmoothness(nodes,
                               divisionsU=divisionsU,
                               divisionsV=divisionsV,
                               pointsWire=pointsWire,
                               pointsShaded=pointsShaded,
                               polygonObject=polygonObject)
        yield
    finally:
        # Revert state
        for node, state in originals.iteritems():
            if state:
                cmds.displaySmoothness(node, **state)


@contextlib.contextmanager
def no_display_layers(nodes):
    """Ensure nodes are not in a displayLayer during context.

    Arguments:
        nodes (list): The nodes to remove from any display layer.

    """

    # Ensure long names
    nodes = cmds.ls(nodes, long=True)

    # Get the original state
    lookup = set(nodes)
    original = {}
    for layer in cmds.ls(type='displayLayer'):

        # Skip default layer
        if layer == "defaultLayer":
            continue

        members = cmds.editDisplayLayerMembers(layer,
                                               query=True,
                                               fullNames=True)
        if not members:
            continue
        members = set(members)

        included = lookup.intersection(members)
        if included:
            original[layer] = list(included)

    try:
        # Add all nodes to default layer
        cmds.editDisplayLayerMembers("defaultLayer", nodes, noRecurse=True)
        yield
    finally:
        # Restore original members
        for layer, members in original.iteritems():
            cmds.editDisplayLayerMembers(layer, members, noRecurse=True)


@contextlib.contextmanager
def namespaced(namespace, new=True):
    """Work inside namespace during context

    Args:
        new (bool): When enabled this will rename the namespace to a unique
            namespace if the input namespace already exists.

    Yields:
        str: The namespace that is used during the context

    """
    original = cmds.namespaceInfo(cur=True)
    if new:
        namespace = avalon.maya.lib.unique_namespace(namespace)
        cmds.namespace(add=namespace)

    try:
        cmds.namespace(set=namespace)
        yield namespace
    finally:
        cmds.namespace(set=original)


@contextlib.contextmanager
def maintained_selection_api():
    """Maintain selection using the Maya Python API.

    Warning: This is *not* added to the undo stack.

    """
    original = om.MGlobal.getActiveSelectionList()
    try:
        yield
    finally:
        om.MGlobal.setActiveSelectionList(original)


def polyConstraint(components, *args, **kwargs):
    """Return the list of *components* with the constraints applied.

    A wrapper around Maya's `polySelectConstraint` to retrieve its results as
    a list without altering selections. For a list of possible constraints
    see `maya.cmds.polySelectConstraint` documentation.

    Arguments:
        components (list): List of components of polygon meshes

    Returns:
        list: The list of components filtered by the given constraints.

    """

    kwargs.pop('mode', None)

    with no_undo(flush=False):
        # Reverting selection to the original selection using
        # `maya.cmds.select` can be slow in rare cases where previously
        # `maya.cmds.polySelectConstraint` had set constrain to "All and Next"
        # and the "Random" setting was activated. To work around this we
        # revert to the original selection using the Maya API. This is safe
        # since we're not generating any undo change anyway.
        with maintained_selection_api():
            # Apply constraint using mode=2 (current and next) so
            # it applies to the selection made before it; because just
            # a `maya.cmds.select()` call will not trigger the constraint.
            with reset_polySelectConstraint():
                cmds.select(components, r=1, noExpand=True)
                cmds.polySelectConstraint(*args, mode=2, **kwargs)
                result = cmds.ls(selection=True)
                cmds.select(clear=True)

    return result


@contextlib.contextmanager
def reset_polySelectConstraint(reset=True):
    """Context during which the given polyConstraint settings are disabled.

    The original settings are restored after the context.

    """

    original = cmds.polySelectConstraint(query=True, stateString=True)

    try:
        if reset:
            # Ensure command is available in mel
            # This can happen when running standalone
            if not mel.eval("exists resetPolySelectConstraint"):
                mel.eval("source polygonConstraint")

            # Reset all parameters
            mel.eval("resetPolySelectConstraint;")
        cmds.polySelectConstraint(disable=True)
        yield
    finally:
        mel.eval(original)


def is_visible(node,
               displayLayer=True,
               intermediateObject=True,
               parentHidden=True,
               visibility=True):
    """Is `node` visible?

    Returns whether a node is hidden by one of the following methods:
    - The node exists (always checked)
    - The node must be a dagNode (always checked)
    - The node's visibility is off.
    - The node is set as intermediate Object.
    - The node is in a disabled displayLayer.
    - Whether any of its parent nodes is hidden.

    Roughly based on: http://ewertb.soundlinker.com/mel/mel.098.php

    Returns:
        bool: Whether the node is visible in the scene

    """

    # Only existing objects can be visible
    if not cmds.objExists(node):
        return False

    # Only dagNodes can be visible
    if not cmds.objectType(node, isAType='dagNode'):
        return False

    if visibility:
        if not cmds.getAttr('{0}.visibility'.format(node)):
            return False

    if intermediateObject and cmds.objectType(node, isAType='shape'):
        if cmds.getAttr('{0}.intermediateObject'.format(node)):
            return False

    if displayLayer:
        # Display layers set overrideEnabled and overrideVisibility on members
        if cmds.attributeQuery('overrideEnabled', node=node, exists=True):
            override_enabled = cmds.getAttr('{}.overrideEnabled'.format(node))
            override_visibility = cmds.getAttr('{}.overrideVisibility'.format(node))
            if override_enabled and override_visibility:
                return False

    if parentHidden:
        parents = cmds.listRelatives(node, parent=True, fullPath=True)
        if parents:
            parent = parents[0]
            if not is_visible(parent,
                              displayLayer=displayLayer,
                              intermediateObject=False,
                              parentHidden=parentHidden,
                              visibility=visibility):
                return False

    return True


def extract_alembic(file,
                    startFrame=None,
                    endFrame=None,
                    selection=True,
                    uvWrite= True,
                    eulerFilter=True,
                    dataFormat="ogawa",
                    verbose=False,
                    **kwargs):
    """Extract a single Alembic Cache.

    This extracts an Alembic cache using the `-selection` flag to minimize
    the extracted content to solely what was Collected into the instance.

    Arguments:

        startFrame (float): Start frame of output. Ignored if `frameRange`
            provided.

        endFrame (float): End frame of output. Ignored if `frameRange`
            provided.

        frameRange (tuple or str): Two-tuple with start and end frame or a
            string formatted as: "startFrame endFrame". This argument
            overrides `startFrame` and `endFrame` arguments.

        dataFormat (str): The data format to use for the cache,
                          defaults to "ogawa"

        verbose (bool): When on, outputs frame number information to the
            Script Editor or output window during extraction.

        noNormals (bool): When on, normal data from the original polygon
            objects is not included in the exported Alembic cache file.

        renderableOnly (bool): When on, any non-renderable nodes or hierarchy,
            such as hidden objects, are not included in the Alembic file.
            Defaults to False.

        stripNamespaces (bool): When on, any namespaces associated with the
            exported objects are removed from the Alembic file. For example, an
            object with the namespace taco:foo:bar appears as bar in the
            Alembic file.

        uvWrite (bool): When on, UV data from polygon meshes and subdivision
            objects are written to the Alembic file. Only the current UV map is
            included.

        worldSpace (bool): When on, the top node in the node hierarchy is
            stored as world space. By default, these nodes are stored as local
            space. Defaults to False.

        eulerFilter (bool): When on, X, Y, and Z rotation data is filtered with
            an Euler filter. Euler filtering helps resolve irregularities in
            rotations especially if X, Y, and Z rotations exceed 360 degrees.
            Defaults to True.

    """

    # Ensure alembic exporter is loaded
    cmds.loadPlugin('AbcExport', quiet=True)

    # Alembic Exporter requires forward slashes
    file = file.replace('\\', '/')

    # Pass the start and end frame on as `frameRange` so that it
    # never conflicts with that argument
    if "frameRange" not in kwargs:
        # Fallback to maya timeline if no start or end frame provided.
        if startFrame is None:
            startFrame = cmds.playbackOptions(query=True,
                                              animationStartTime=True)
        if endFrame is None:
            endFrame = cmds.playbackOptions(query=True,
                                            animationEndTime=True)

        # Ensure valid types are converted to frame range
        assert isinstance(startFrame, _alembic_options["startFrame"])
        assert isinstance(endFrame, _alembic_options["endFrame"])
        kwargs["frameRange"] = "{0} {1}".format(startFrame, endFrame)
    else:
        # Allow conversion from tuple for `frameRange`
        frame_range = kwargs["frameRange"]
        if isinstance(frame_range, (list, tuple)):
            assert len(frame_range) == 2
            kwargs["frameRange"] = "{0} {1}".format(frame_range[0],
                                                    frame_range[1])

    # Assemble options
    options = {
        "selection": selection,
        "uvWrite": uvWrite,
        "eulerFilter": eulerFilter,
        "dataFormat": dataFormat
    }
    options.update(kwargs)

    # Validate options
    for key, value in options.copy().items():

        # Discard unknown options
        if key not in _alembic_options:
            log.warning("extract_alembic() does not support option '%s'. "
                        "Flag will be ignored..", key)
            options.pop(key)
            continue

        # Validate value type
        valid_types = _alembic_options[key]
        if not isinstance(value, valid_types):
            raise TypeError("Alembic option unsupported type: "
                            "{0} (expected {1})".format(value, valid_types))

        # Ignore empty values, like an empty string, since they mess up how
        # job arguments are built
        if isinstance(value, (list, tuple)):
            value = [x for x in value if x.strip()]

            # Ignore option completely if no values remaining
            if not value:
                options.pop(key)
                continue

            options[key] = value

    # The `writeCreases` argument was changed to `autoSubd` in Maya 2018+
    maya_version = int(cmds.about(version=True))
    if maya_version >= 2018:
        options['autoSubd'] = options.pop('writeCreases', False)

    # Format the job string from options
    job_args = list()
    for key, value in options.items():
        if isinstance(value, (list, tuple)):
            for entry in value:
                job_args.append("-{} {}".format(key, entry))
        elif isinstance(value, bool):
            # Add only when state is set to True
            if value:
                job_args.append("-{0}".format(key))
        else:
            job_args.append("-{0} {1}".format(key, value))

    job_str = " ".join(job_args)
    job_str += ' -file "%s"' % file

    # Ensure output directory exists
    parent_dir = os.path.dirname(file)
    if not os.path.exists(parent_dir):
        os.makedirs(parent_dir)

    if verbose:
        log.debug("Preparing Alembic export with options: %s",
                  json.dumps(options, indent=4))
        log.debug("Extracting Alembic with job arguments: %s", job_str)

    # Perform extraction
    print("Alembic Job Arguments : {}".format(job_str))

    # Disable the parallel evaluation temporarily to ensure no buggy
    # exports are made. (PLN-31)
    # TODO: Make sure this actually fixes the issues
    with evaluation("off"):
        cmds.AbcExport(j=job_str, verbose=verbose)

    if verbose:
        log.debug("Extracted Alembic to: %s", file)

    return file


def maya_temp_folder():
    scene_dir = os.path.dirname(cmds.file(query=True, sceneName=True))
    tmp_dir = os.path.abspath(os.path.join(scene_dir, "..", "tmp"))
    if not os.path.isdir(tmp_dir):
        os.makedirs(tmp_dir)

    return tmp_dir


# region ID
def get_id_required_nodes(referenced_nodes=False, nodes=None):
    """Filter out any node which are locked (reference) or readOnly

    Args:
        referenced_nodes (bool): set True to filter out reference nodes
        nodes (list, Optional): nodes to consider
    Returns:
        nodes (set): list of filtered nodes
    """

    lookup = None
    if nodes is None:
        # Consider all nodes
        nodes = cmds.ls()
    else:
        # Build a lookup for the only allowed nodes in output based
        # on `nodes` input of the function (+ ensure long names)
        lookup = set(cmds.ls(nodes, long=True))

    def _node_type_exists(node_type):
        try:
            cmds.nodeType(node_type, isTypeName=True)
            return True
        except RuntimeError:
            return False

    # `readOnly` flag is obsolete as of Maya 2016 therefore we explicitly
    # remove default nodes and reference nodes
    camera_shapes = ["frontShape", "sideShape", "topShape", "perspShape"]

    ignore = set()
    if not referenced_nodes:
        ignore |= set(cmds.ls(long=True, referencedNodes=True))

    # list all defaultNodes to filter out from the rest
    ignore |= set(cmds.ls(long=True, defaultNodes=True))
    ignore |= set(cmds.ls(camera_shapes, long=True))

    # Remove Turtle from the result of `cmds.ls` if Turtle is loaded
    # TODO: This should be a less specific check for a single plug-in.
    if _node_type_exists("ilrBakeLayer"):
        ignore |= set(cmds.ls(type="ilrBakeLayer", long=True))

    # Establish set of nodes types to include
    types = ["objectSet", "file", "mesh", "nurbsCurve", "nurbsSurface"]

    # Check if plugin nodes are available for Maya by checking if the plugin
    # is loaded
    if cmds.pluginInfo("pgYetiMaya",  query=True, loaded=True):
        types.append("pgYetiMaya")

    # We *always* ignore intermediate shapes, so we filter them out directly
    nodes = cmds.ls(nodes, type=types, long=True, noIntermediate=True)

    # The items which need to pass the id to their parent
    # Add the collected transform to the nodes
    dag = cmds.ls(nodes, type="dagNode", long=True)  # query only dag nodes
    transforms = cmds.listRelatives(dag,
                                    parent=True,
                                    fullPath=True) or []

    nodes = set(nodes)
    nodes |= set(transforms)

    nodes -= ignore  # Remove the ignored nodes
    if not nodes:
        return nodes

    # Ensure only nodes from the input `nodes` are returned when a
    # filter was applied on function call because we also iterated
    # to parents and alike
    if lookup is not None:
        nodes &= lookup

    # Avoid locked nodes
    nodes_list = list(nodes)
    locked = cmds.lockNode(nodes_list, query=True, lock=True)
    for node, lock in zip(nodes_list, locked):
        if lock:
            log.warning("Skipping locked node: %s" % node)
            nodes.remove(node)

    return nodes


def get_id(node):
    """
    Get the `cbId` attribute of the given node
    Args:
        node (str): the name of the node to retrieve the attribute from

    Returns:
        str

    """

    if node is None:
        return

    sel = om.MSelectionList()
    sel.add(node)

    api_node = sel.getDependNode(0)
    fn = om.MFnDependencyNode(api_node)

    if not fn.hasAttribute("cbId"):
        return

    try:
        return fn.findPlug("cbId", False).asString()
    except RuntimeError:
        log.warning("Failed to retrieve cbId on %s", node)
        return


def generate_ids(nodes, asset_id=None):
    """Returns new unique ids for the given nodes.

    Note: This does not assign the new ids, it only generates the values.

    To assign new ids using this method:
    >>> nodes = ["a", "b", "c"]
    >>> for node, id in generate_ids(nodes):
    >>>     set_id(node, id)

    To also override any existing values (and assign regenerated ids):
    >>> nodes = ["a", "b", "c"]
    >>> for node, id in generate_ids(nodes):
    >>>     set_id(node, id, overwrite=True)

    Args:
        nodes (list): List of nodes.
        asset_id (str or bson.ObjectId): The database id for the *asset* to
            generate for. When None provided the current asset in the
            active session is used.

    Returns:
        list: A list of (node, id) tuples.

    """

    if asset_id is None:
        # Get the asset ID from the database for the asset of current context
        asset_data = io.find_one({"type": "asset",
                                  "name": api.Session["AVALON_ASSET"]},
                                 projection={"_id": True})
        assert asset_data, "No current asset found in Session"
        asset_id = asset_data['_id']

    node_ids = []
    for node in nodes:
        _, uid = str(uuid.uuid4()).rsplit("-", 1)
        unique_id = "{}:{}".format(asset_id, uid)
        node_ids.append((node, unique_id))

    return node_ids


def set_id(node, unique_id, overwrite=False):
    """Add cbId to `node` unless one already exists.

    Args:
        node (str): the node to add the "cbId" on
        unique_id (str): The unique node id to assign.
            This should be generated by `generate_ids`.
        overwrite (bool, optional): When True overrides the current value even
            if `node` already has an id. Defaults to False.

    Returns:
        None

    """

    exists = cmds.attributeQuery("cbId", node=node, exists=True)

    # Add the attribute if it does not exist yet
    if not exists:
        cmds.addAttr(node, longName="cbId", dataType="string")

    # Set the value
    if not exists or overwrite:
        attr = "{0}.cbId".format(node)
        cmds.setAttr(attr, unique_id, type="string")


def remove_id(node):
    """Remove the id attribute from the input node.

    Args:
        node (str): The node name

    Returns:
        bool: Whether an id attribute was deleted

    """
    if cmds.attributeQuery("cbId", node=node, exists=True):
        cmds.deleteAttr("{}.cbId".format(node))
        return True
    return False


# endregion ID
def get_reference_node(path):
    """
    Get the reference node when the path is found being used in a reference
    Args:
        path (str): the file path to check

    Returns:
        node (str): name of the reference node in question
    """
    try:
        node = cmds.file(path, query=True, referenceNode=True)
    except RuntimeError:
        log.debug('File is not referenced : "{}"'.format(path))
        return

    reference_path = cmds.referenceQuery(path, filename=True)
    if os.path.normpath(path) == os.path.normpath(reference_path):
        return node


def set_attribute(attribute, value, node):
    """Adjust attributes based on the value from the attribute data

    If an attribute does not exists on the target it will be added with
    the dataType being controlled by the value type.

    Args:
        attribute (str): name of the attribute to change
        value: the value to change to attribute to
        node (str): name of the node

    Returns:
        None
    """

    value_type = type(value).__name__
    kwargs = ATTRIBUTE_DICT[value_type]
    if not cmds.attributeQuery(attribute, node=node, exists=True):
        log.debug("Creating attribute '{}' on "
                  "'{}'".format(attribute, node))
        cmds.addAttr(node, longName=attribute, **kwargs)

    node_attr = "{}.{}".format(node, attribute)
    if "dataType" in kwargs:
        attr_type = kwargs["dataType"]
        cmds.setAttr(node_attr, value, type=attr_type)
    else:
        cmds.setAttr(node_attr, value)


def apply_attributes(attributes, nodes_by_id):
    """Alter the attributes to match the state when publishing

    Apply attribute settings from the publish to the node in the scene based
    on the UUID which is stored in the cbId attribute.

    Args:
        attributes (list): list of dictionaries
        nodes_by_id (dict): collection of nodes based on UUID
                           {uuid: [node, node]}

    """

    for attr_data in attributes:
        nodes = nodes_by_id[attr_data["uuid"]]
        attr_value = attr_data["attributes"]
        for node in nodes:
            for attr, value in attr_value.items():
                set_attribute(attr, value, node)


# region LOOKDEV
def list_looks(asset_id):
    """Return all look subsets for the given asset

    This assumes all look subsets start with "look*" in their names.
    """

    # Get all subsets with look leading in
    # the name associated with the asset
    subsets = io.find({"parent": io.ObjectId(asset_id),
                       "type": "subset",
                       "name": {"$regex": "look*"}})
    subsets = list(subsets)

    # Now ensure it's actually really a subset that contains `colorbleed.look`
    # family. Since #443 this wouldn't have to be done separately, but we are
    # still doing so for backwards compatibility.
    look_family = "colorbleed.look"
    look_subsets = []
    for subset in subsets:
        # Subsets that based on schema "avalon-core:subset-3.0" have
        # families directly inside it, see #443.
        if subset.get("schema") == "avalon-core:subset-3.0":
            if look_family in subset["data"]["families"]:
                look_subsets.append(subset)
        else:
            # Backwards compatibility for older subset version that only
            # had families stored in the version data.
            if io.find_one({"data.families": look_family,
                            "parent": subset["_id"]},
                           # Optimization: Use empty projection list so it
                           # only returns the id instead of full data for the
                           # version
                           projection=list()):
                look_subsets.append(subset)

    return look_subsets


def assign_look_by_version(nodes, version_id):
    """Assign nodes a specific published look version by id.

    This assumes the nodes correspond with the asset.

    Args:
        nodes(list): nodes to assign look to
        version_id (bson.ObjectId): database id of the version

    Returns:
        None
    """

    # Get representations of shader file and relationships
    look_representation = io.find_one({"type": "representation",
                                       "parent": version_id,
                                       "name": "ma"})

    json_representation = io.find_one({"type": "representation",
                                       "parent": version_id,
                                       "name": "json"})

    # See if representation is already loaded, if so reuse it.
    host = api.registered_host()
    representation_id = str(look_representation['_id'])
    for container in host.ls():
        if (container['loader'] == "LookLoader" and
                container['representation'] == representation_id):
            log.info("Reusing loaded look ..")
            container_node = container['objectName']
            break
    else:
        log.info("Using look for the first time ..")

        # Load file
        loaders = api.loaders_from_representation(api.discover(api.Loader),
                                                  representation_id)
        Loader = next((i for i in loaders if i.__name__ == "LookLoader"), None)
        if Loader is None:
            raise RuntimeError("Could not find LookLoader, this is a bug")

        # Reference the look file
        with maya.maintained_selection():
            container_node = pipeline.load(Loader, look_representation)

    # Get container members
    shader_nodes = cmds.sets(container_node, query=True)

    # Load relationships
    shader_relation = api.get_representation_path(json_representation)
    with open(shader_relation, "r") as f:
        relationships = json.load(f)

    # Assign relationships
    apply_shaders(relationships, shader_nodes, nodes)


def assign_look(nodes, subset="lookDefault"):
    """Assigns a look to a node.

    Optimizes the nodes by grouping by asset id and finding
    related subset by name.

    Args:
        nodes (list): all nodes to assign the look to
        subset (str): name of the subset to find
    """

    # Group all nodes per asset id
    grouped = defaultdict(list)
    for node in nodes:
        colorbleed_id = get_id(node)
        if not colorbleed_id:
            continue

        parts = colorbleed_id.split(":", 1)
        grouped[parts[0]].append(node)

    for asset_id, asset_nodes in grouped.items():
        # create objectId for database
        try:
            asset_id = bson.ObjectId(asset_id)
        except bson.errors.InvalidId:
            log.warning("Asset ID is not compatible with bson")
            continue
        subset_data = io.find_one({"type": "subset",
                                   "name": subset,
                                   "parent": asset_id})

        if not subset_data:
            log.warning("No subset '{}' found for {}".format(subset, asset_id))
            continue

        # get last version
        # with backwards compatibility
        version = io.find_one({"parent": subset_data['_id'],
                               "type": "version",
                               "data.families":
                                   {"$in": ["colorbleed.look"]}
                               },
                              sort=[("name", -1)],
                              projection={"_id": True, "name": True})

        log.debug("Assigning look '{}' <v{:03d}>".format(subset,
                                                         version["name"]))

        assign_look_by_version(asset_nodes, version['_id'])


def apply_shaders(relationships, shadernodes, nodes):
    """Link shadingEngine to the right nodes based on relationship data

    Relationship data is constructed of a collection of `sets` and `attributes`
    `sets` corresponds with the shaderEngines found in the lookdev.
    Each set has the keys `name`, `members` and `uuid`, the `members`
    hold a collection of node information `name` and `uuid`.

    Args:
        relationships (dict): relationship data
        shadernodes (list): list of nodes of the shading objectSets (includes
        VRayObjectProperties and shadingEngines)
        nodes (list): list of nodes to apply shader to

    Returns:
        None
    """

    attributes = relationships.get("attributes", [])
    shader_data = relationships.get("relationships", {})

    shading_engines = cmds.ls(shadernodes, type="objectSet", long=True)
    assert shading_engines, "Error in retrieving objectSets from reference"

    # region compute lookup
    nodes_by_id = defaultdict(list)
    for node in nodes:
        nodes_by_id[get_id(node)].append(node)

    shading_engines_by_id = defaultdict(list)
    for shad in shading_engines:
        shading_engines_by_id[get_id(shad)].append(shad)
    # endregion

    # region assign shading engines and other sets
    for data in shader_data.values():
        # collect all unique IDs of the set members
        shader_uuid = data["uuid"]
        member_uuids = [member["uuid"] for member in data["members"]]

        filtered_nodes = list()
        for uuid in member_uuids:
            filtered_nodes.extend(nodes_by_id[uuid])

        id_shading_engines = shading_engines_by_id[shader_uuid]
        if not id_shading_engines:
            log.error("No shader found with cbId "
                      "'{}'".format(shader_uuid))
            continue
        elif len(id_shading_engines) > 1:
            log.error("Skipping shader assignment. "
                      "More than one shader found with cbId "
                      "'{}'. (found: {})".format(shader_uuid,
                                                 id_shading_engines))
            continue

        if not filtered_nodes:
            log.warning("No nodes found for shading engine "
                        "'{0}'".format(id_shading_engines[0]))
            continue

        cmds.sets(filtered_nodes, forceElement=id_shading_engines[0])
    # endregion

    apply_attributes(attributes, nodes_by_id)


# endregion LOOKDEV
def get_isolate_view_sets():
    """Return isolate view sets of all modelPanels.

    Returns:
        list: all sets related to isolate view

    """

    view_sets = set()
    for panel in cmds.getPanel(type="modelPanel") or []:
        view_set = cmds.modelEditor(panel, query=True, viewObjects=True)
        if view_set:
            view_sets.add(view_set)

    return view_sets


def get_related_sets(node):
    """Return objectSets that are relationships for a look for `node`.

    Filters out based on:
    - id attribute is NOT `pyblish.avalon.container`
    - shapes and deformer shapes (alembic creates meshShapeDeformed)
    - set name ends with any from a predefined list
    - set in not in viewport set (isolate selected for example)

    Args:
        node (str): name of the current node to check

    Returns:
        list: The related sets

    """

    # Ignore specific suffices
    ignore_suffices = ["out_SET", "controls_SET", "_INST", "_CON"]

    # Default nodes to ignore
    defaults = {"defaultLightSet", "defaultObjectSet"}

    # Ids to ignore
    ignored = {"pyblish.avalon.instance", "pyblish.avalon.container"}

    view_sets = get_isolate_view_sets()

    sets = cmds.listSets(object=node, extendToShape=False)
    if not sets:
        return []

    # Fix 'no object matches name' errors on nodes returned by listSets.
    # In rare cases it can happen that a node is added to an internal maya
    # set inaccessible by maya commands, for example check some nodes
    # returned by `cmds.listSets(allSets=True)`
    sets = cmds.ls(sets)

    # Ignore `avalon.container`
    sets = [s for s in sets if
            not cmds.attributeQuery("id", node=s, exists=True) or
            not cmds.getAttr("%s.id" % s) in ignored]

    # Exclude deformer sets (`type=2` for `maya.cmds.listSets`)
    deformer_sets = cmds.listSets(object=node,
                                  extendToShape=False,
                                  type=2) or []
    deformer_sets = set(deformer_sets)  # optimize lookup
    sets = [s for s in sets if s not in deformer_sets]

    # Ignore when the set has a specific suffix
    sets = [s for s in sets if not any(s.endswith(x) for x in ignore_suffices)]

    # Ignore viewport filter view sets (from isolate select and
    # viewports)
    sets = [s for s in sets if s not in view_sets]
    sets = [s for s in sets if s not in defaults]

    return sets


def get_container_transforms(container, members=None, root=False):
    """Retrieve the root node of the container content

    When a container is created through a Loader the content
    of the file will be grouped under a transform. The name of the root
    transform is stored in the container information

    Args:
        container (dict): the container
        members (list): optional and convenience argument
        root (bool): return highest node in hierachy if True

    Returns:
        root (list / str):
    """

    if not members:
        members = cmds.sets(container["objectName"], query=True)

    results = cmds.ls(members, type="transform", long=True)
    if root:
        root = get_highest_in_hierarchy(results)
        if root:
            results = root[0]

    return results


def get_highest_in_hierarchy(nodes):
    """Return highest nodes in the hierarchy that are in the `nodes` list.

    The "highest in hierarchy" are the nodes closest to world: top-most level.
    This filters out nodes that are children of others in the input `nodes`.

    Args:
        nodes (list): The nodes in which find the highest in hierarchies.

    Returns:
        list: The highest nodes from the input nodes.

    """

    # Ensure we use long names
    nodes = cmds.ls(nodes, long=True)
    lookup = set(nodes)

    highest = []
    for node in nodes:
        # If no parents are within the nodes input list
        # then this is a highest node
        if not any(n in lookup for n in iter_parents(node)):
            highest.append(node)

    return highest


def iter_parents(node):
    """Iter parents of node from its long name.

    Note: The `node` *must* be the long node name.

    Args:
        node (str): Node long name.

    Yields:
        str: All parent node names (long names)

    """
    while True:
        split = node.rsplit("|", 1)
        if len(split) == 1:
            return

        node = split[0]
        yield node


def remove_other_uv_sets(mesh):
    """Remove all other UV sets than the current UV set.

    Keep only current UV set and ensure it's the renamed to default 'map1'.

    """

    uvSets = cmds.polyUVSet(mesh, query=True, allUVSets=True)
    current = cmds.polyUVSet(mesh, query=True, currentUVSet=True)[0]

    # Copy over to map1
    if current != 'map1':
        cmds.polyUVSet(mesh, uvSet=current, newUVSet='map1', copy=True)
        cmds.polyUVSet(mesh, currentUVSet=True, uvSet='map1')
        current = 'map1'

    # Delete all non-current UV sets
    deleteUVSets = [uvSet for uvSet in uvSets if uvSet != current]
    uvSet = None

    # Maya Bug (tested in 2015/2016):
    # In some cases the API's MFnMesh will report less UV sets than
    # maya.cmds.polyUVSet. This seems to happen when the deletion of UV sets
    # has not triggered a cleanup of the UVSet array attribute on the mesh
    # node. It will still have extra entries in the attribute, though it will
    # not show up in API or UI. Nevertheless it does show up in
    # maya.cmds.polyUVSet. To ensure we clean up the array we'll force delete
    # the extra remaining 'indices' that we don't want.

    # TODO: Implement a better fix
    # The best way to fix would be to get the UVSet indices from api with
    # MFnMesh (to ensure we keep correct ones) and then only force delete the
    # other entries in the array attribute on the node. But for now we're
    # deleting all entries except first one. Note that the first entry could
    # never be removed (the default 'map1' always exists and is supposed to
    # be undeletable.)
    try:
        for uvSet in deleteUVSets:
            cmds.polyUVSet(mesh, delete=True, uvSet=uvSet)
    except RuntimeError as exc:
        log.warning('Error uvSet: %s - %s', uvSet, exc)
        indices = cmds.getAttr('{0}.uvSet'.format(mesh),
                               multiIndices=True)
        if not indices:
            log.warning("No uv set found indices for: %s", mesh)
            return

        # Delete from end to avoid shifting indices
        # and remove the indices in the attribute
        indices = reversed(indices[1:])
        for i in indices:
            attr = '{0}.uvSet[{1}]'.format(mesh, i)
            cmds.removeMultiInstance(attr, b=True)


def get_id_from_history(node):
    """Return first node id in the history chain that matches this node.

    The nodes in history must be of the exact same node type and must be
    parented under the same parent.

    Args:
        node (str): node to retrieve the

    Returns:
        str or None: The id from the node in history or None when no id found
            on any valid nodes in the history.

    """

    def _get_parent(node):
        """Return full path name for parent of node"""
        return cmds.listRelatives(node, parent=True, fullPath=True)

    node = cmds.ls(node, long=True)[0]

    # Find all similar nodes in history
    history = cmds.listHistory(node)
    node_type = cmds.nodeType(node)
    similar_nodes = cmds.ls(history, exactType=node_type, long=True)

    # Exclude itself
    similar_nodes = [x for x in similar_nodes if x != node]

    # The node *must be* under the same parent
    parent = _get_parent(node)
    similar_nodes = [i for i in similar_nodes if _get_parent(i) == parent]

    # Check all of the remaining similar nodes and take the first one
    # with an id and assume it's the original.
    for similar_node in similar_nodes:
        _id = get_id(similar_node)
        if _id:
            return _id


# Project settings
def set_scene_fps(fps, update=True):
    """Set FPS from project configuration

    Args:
        fps (int, float): desired FPS
        update(bool): toggle update animation, default is True

    Returns:
        None

    """

    if fps in FLOAT_FPS:
        unit = "{}fps".format(fps)

    elif fps in INT_FPS:
        unit = "{}fps".format(int(fps))

    else:
        raise ValueError("Unsupported FPS value: `%s`" % fps)

    # Get time slider current state
    start_frame = cmds.playbackOptions(query=True, minTime=True)
    end_frame = cmds.playbackOptions(query=True, maxTime=True)

    # Get animation data
    animation_start = cmds.playbackOptions(query=True, animationStartTime=True)
    animation_end = cmds.playbackOptions(query=True, animationEndTime=True)

    current_frame = cmds.currentTime(query=True)

    log.info("Setting scene FPS to: '{}' "
             "(update keys: {})".format(unit, update))
    cmds.currentUnit(time=unit, updateAnimation=update)

    # Set time slider data back to previous state
    cmds.playbackOptions(edit=True, minTime=start_frame)
    cmds.playbackOptions(edit=True, maxTime=end_frame)

    # Set animation data
    cmds.playbackOptions(edit=True, animationStartTime=animation_start)
    cmds.playbackOptions(edit=True, animationEndTime=animation_end)

    cmds.currentTime(current_frame, edit=True, update=True)

    # Force file stated to 'modified'
    cmds.file(modified=True)


def set_scene_resolution(width, height):
    """Set the render resolution

    Args:
        width(int): value of the width
        height(int): value of the height

    Returns:
        None

    """

    control_node = "defaultResolution"
    current_renderer = cmds.getAttr("defaultRenderGlobals.currentRenderer")

    # Give VRay a helping hand as it is slightly different from the rest
    if current_renderer == "vray":
        vray_node = "vraySettings"
        if cmds.objExists(vray_node):
            control_node = vray_node
        else:
            log.error("Can't set VRay resolution because there is no node "
                      "named: `%s`" % vray_node)

    log.info("Setting scene resolution to: %s x %s" % (width, height))
    cmds.setAttr("%s.width" % control_node, width)
    cmds.setAttr("%s.height" % control_node, height)


def set_context_settings():
    """Apply the project settings from the project definition

    Settings can be overwritten by an asset if the asset.data contains
    any information regarding those settings.

    Examples of settings:
        fps
        resolution
        renderer

    Returns:
        None
    """

    # Todo (Wijnand): apply renderer and resolution of project

    project_data = lib.get_project_data()
    asset_data = lib.get_asset_data()

    # Set project fps
    fps = asset_data.get("fps", project_data.get("fps", 25))
    set_scene_fps(fps)

    # Set project resolution
    width_key = "resolution_width"
    height_key = "resolution_height"

    width = asset_data.get(width_key, project_data.get(width_key, 1920))
    height = asset_data.get(height_key, project_data.get(height_key, 1080))

    set_scene_resolution(width, height)


# Valid FPS
def validate_fps():
    """Validate current scene FPS and show pop-up when it is incorrect

    Returns:
        bool

    """

    fps = lib.get_asset_fps()
    current_fps = mel.eval('currentTimeUnitToFPS()')  # returns float

    if current_fps != fps:

        from avalon.vendor.Qt import QtWidgets
        from ..widgets import popup

        # Find maya main window
        top_level_widgets = {w.objectName(): w for w in
                             QtWidgets.QApplication.topLevelWidgets()}

        parent = top_level_widgets.get("MayaWindow", None)
        if parent is None:
            pass
        else:
            dialog = popup.PopupUpdateKeys(parent=parent)
            dialog.setModal(True)
            dialog.setWindowTitle("Maya scene does not match project FPS")
            dialog.setMessage("Scene %i FPS does not match project %i FPS" %
                              (current_fps, fps))
            dialog.setButtonText("Fix")

            # on_show is the Fix button clicked callback
            callback = lambda update: set_scene_fps(fps, update)
            dialog.on_clicked_state.connect(callback)

            dialog.show()

            return False

    return True


def bake(nodes,
         frame_range=None,
         step=1.0,
         simulation=True,
         preserve_outside_keys=False,
         disable_implicit_control=True,
         shape=True):
    """Bake the given nodes over the time range.

    This will bake all attributes of the node, including custom attributes.

    Args:
        nodes (list): Names of transform nodes, eg. camera, light.
        frame_range (list): frame range with start and end frame.
            or if None then takes timeSliderRange
        simulation (bool): Whether to perform a full simulation of the
            attributes over time.
        preserve_outside_keys (bool): Keep keys that are outside of the baked
            range.
        disable_implicit_control (bool): When True will disable any
            constraints to the object.
        shape (bool): When True also bake attributes on the children shapes.
        step (float): The step size to sample by.

    Returns:
        None

    """

    # Parse inputs
    if not nodes:
        return

    assert isinstance(nodes, (list, tuple)), "Nodes must be a list or tuple"

    # If frame range is None fall back to time slider playback time range
    if frame_range is None:
        frame_range = [cmds.playbackOptions(query=True, minTime=True),
                       cmds.playbackOptions(query=True, maxTime=True)]

    # If frame range is single frame bake one frame more,
    # otherwise maya.cmds.bakeResults gets confused
    if frame_range[1] == frame_range[0]:
        frame_range[1] += 1

    # Bake it
    with keytangent_default(in_tangent_type='auto',
                            out_tangent_type='auto'):
        cmds.bakeResults(nodes,
                         simulation=simulation,
                         preserveOutsideKeys=preserve_outside_keys,
                         disableImplicitControl=disable_implicit_control,
                         shape=shape,
                         sampleBy=step,
                         time=(frame_range[0], frame_range[1]))


def bake_to_world_space(nodes,
                        frame_range=None,
                        simulation=True,
                        preserve_outside_keys=False,
                        disable_implicit_control=True,
                        shape=True,
                        step=1.0):
    """Bake the nodes to world space transformation (incl. other attributes)

    Bakes the transforms to world space (while maintaining all its animated
    attributes and settings) by duplicating the node. Then parents it to world
    and constrains to the original.

    Other attributes are also baked by connecting all attributes directly.
    Baking is then done using Maya's bakeResults command.

    See `bake` for the argument documentation.

    Returns:
         list: The newly created and baked node names.

    """

    def _get_attrs(node):
        """Workaround for buggy shape attribute listing with listAttr"""
        attrs = cmds.listAttr(node,
                              write=True,
                              scalar=True,
                              settable=True,
                              connectable=True,
                              keyable=True,
                              shortNames=True) or []
        valid_attrs = []
        for attr in attrs:
            node_attr = '{0}.{1}'.format(node, attr)

            # Sometimes Maya returns 'non-existent' attributes for shapes
            # so we filter those out
            if not cmds.attributeQuery(attr, node=node, exists=True):
                continue

            # We only need those that have a connection, just to be safe
            # that it's actually keyable/connectable anyway.
            if cmds.connectionInfo(node_attr,
                                   isDestination=True):
                valid_attrs.append(attr)

        return valid_attrs

    transform_attrs = set(["t", "r", "s",
                           "tx", "ty", "tz",
                           "rx", "ry", "rz",
                           "sx", "sy", "sz"])

    world_space_nodes = []
    with delete_after() as delete_bin:

        # Create the duplicate nodes that are in world-space connected to
        # the originals
        for node in nodes:

            # Duplicate the node
            short_name = node.rsplit("|", 1)[-1]
            new_name = "{0}_baked".format(short_name)
            new_node = cmds.duplicate(node,
                                      name=new_name,
                                      renameChildren=True)[0]

            # Connect all attributes on the node except for transform
            # attributes
            attrs = _get_attrs(node)
            attrs = set(attrs) - transform_attrs if attrs else []

            for attr in attrs:
                orig_node_attr = '{0}.{1}'.format(node, attr)
                new_node_attr = '{0}.{1}'.format(new_node, attr)

                # unlock to avoid connection errors
                cmds.setAttr(new_node_attr, lock=False)

                cmds.connectAttr(orig_node_attr,
                                 new_node_attr,
                                 force=True)

            # If shapes are also baked then connect those keyable attributes
            if shape:
                children_shapes = cmds.listRelatives(new_node,
                                                     children=True,
                                                     fullPath=True,
                                                     shapes=True)
                if children_shapes:
                    orig_children_shapes = cmds.listRelatives(node,
                                                              children=True,
                                                              fullPath=True,
                                                              shapes=True)
                    for orig_shape, new_shape in zip(orig_children_shapes,
                                                     children_shapes):
                        attrs = _get_attrs(orig_shape)
                        for attr in attrs:
                            orig_node_attr = '{0}.{1}'.format(orig_shape, attr)
                            new_node_attr = '{0}.{1}'.format(new_shape, attr)

                            # unlock to avoid connection errors
                            cmds.setAttr(new_node_attr, lock=False)

                            cmds.connectAttr(orig_node_attr,
                                             new_node_attr,
                                             force=True)

            # Parent to world
            if cmds.listRelatives(new_node, parent=True):
                new_node = cmds.parent(new_node, world=True)[0]

            # Unlock transform attributes so constraint can be created
            for attr in transform_attrs:
                cmds.setAttr('{0}.{1}'.format(new_node, attr), lock=False)

            # Constraints
            delete_bin.extend(cmds.parentConstraint(node, new_node, mo=False))
            delete_bin.extend(cmds.scaleConstraint(node, new_node, mo=False))

            world_space_nodes.append(new_node)

        bake(world_space_nodes,
             frame_range=frame_range,
             step=step,
             simulation=simulation,
             preserve_outside_keys=preserve_outside_keys,
             disable_implicit_control=disable_implicit_control,
             shape=shape)

    return world_space_nodes


def get_attr_in_layer(attr, layer):
    """Return attribute value in specified renderlayer.

    Same as cmds.getAttr but this gets the attribute's value in a
    given render layer without having to switch to it.

    Warning for parent attribute overrides:
        Attributes that have render layer overrides to their parent attribute
        are not captured correctly since they do not have a direct connection.
        For example, an override to sphere.rotate when querying sphere.rotateX
        will not return correctly!

    Note: This is much faster for Maya's renderLayer system, yet the code
        does no optimized query for render setup.

    Args:
        attr (str): attribute name, ex. "node.attribute"
        layer (str): layer name

    Returns:
        The return value from `maya.cmds.getAttr`

    """

    if cmds.mayaHasRenderSetup():
        log.debug("lib.get_attr_in_layer is not optimized for render setup")
        with renderlayer(layer):
            return cmds.getAttr(attr)

    # Ignore complex query if we're in the layer anyway
    current_layer = cmds.editRenderLayerGlobals(query=True,
                                                currentRenderLayer=True)
    if layer == current_layer:
        return cmds.getAttr(attr)

    connections = cmds.listConnections(attr,
                                       plugs=True,
                                       source=False,
                                       destination=True,
                                       type="renderLayer") or []
    connections = filter(lambda x: x.endswith(".plug"), connections)
    if not connections:
        return cmds.getAttr(attr)

    # Some value types perform a conversion when assigning
    # TODO: See if there's a maya method to allow this conversion
    # instead of computing it ourselves.
    attr_type = cmds.getAttr(attr, type=True)
    conversion = None
    if attr_type == "time":
        conversion = mel.eval('currentTimeUnitToFPS()')  # returns float
    elif attr_type == "doubleAngle":
        # Radians to Degrees: 180 / pi
        # TODO: This will likely only be correct when Maya units are set
        #       to degrees
        conversion = 57.2957795131
    elif attr_type == "doubleLinear":
        raise NotImplementedError("doubleLinear conversion not implemented.")

    for connection in connections:
        if connection.startswith(layer + "."):
            attr_split = connection.split(".")
            if attr_split[0] == layer:
                attr = ".".join(attr_split[0:-1])
                value = cmds.getAttr("%s.value" % attr)
                if conversion:
                    value *= conversion
                return value

    else:
        # When connections are present, but none
        # to the specific renderlayer than the layer
        # should have the "defaultRenderLayer"'s value
        layer = "defaultRenderLayer"
        for connection in connections:
            if connection.startswith(layer):
                attr_split = connection.split(".")
                if attr_split[0] == "defaultRenderLayer":
                    attr = ".".join(attr_split[0:-1])
                    value = cmds.getAttr("%s.value" % attr)
                    if conversion:
                        value *= conversion
                    return value

    return cmds.getAttr(attr)


def get_shader_in_layer(node, layer):
    """Return the assigned shader in a renderlayer without switching layers.

    This has been developed and tested for Legacy Renderlayers and *not* for
    Render Setup.

    Note: This will also return the shader for any face assignments, however
        it will *not* return the components they are assigned to. This could
        be implemented, but since Maya's renderlayers are famous for breaking
        with face assignments there has been no need for this function to
        support that.

    Returns:
        list: The list of assigned shaders in the given layer.

    """

    def _get_shader(shape):
        """Return current shader"""
        return cmds.listConnections(shape + ".instObjGroups",
                                    source=False,
                                    destination=True,
                                    plugs=False,
                                    connections=False,
                                    type="shadingEngine") or []

    # We check the instObjGroups (shader connection) for layer overrides.
    attr = node + ".instObjGroups"

    # Ignore complex query if we're in the layer anyway (optimization)
    current_layer = cmds.editRenderLayerGlobals(query=True,
                                                currentRenderLayer=True)
    if layer == current_layer:
        return _get_shader(node)

    connections = cmds.listConnections(attr,
                                       plugs=True,
                                       source=False,
                                       destination=True,
                                       type="renderLayer") or []
    connections = filter(lambda x: x.endswith(".outPlug"), connections)
    if not connections:
        # If no overrides anywhere on the shader, just get the current shader
        return _get_shader(node)

    def _get_override(connections, layer):
        """Return the overridden connection for that layer in connections"""
        # If there's an override on that layer, return that.
        for connection in connections:
            if (connection.startswith(layer + ".outAdjustments") and
                    connection.endswith(".outPlug")):

                # This is a shader override on that layer so get the shader
                # connected to .outValue of the .outAdjustment[i]
                out_adjustment = connection.rsplit(".", 1)[0]
                connection_attr = out_adjustment + ".outValue"
                override = cmds.listConnections(connection_attr) or []

                return override

    override_shader = _get_override(connections, layer)
    if override_shader is not None:
        return override_shader
    else:
        # Get the override for "defaultRenderLayer" (=masterLayer)
        return _get_override(connections, layer="defaultRenderLayer")


@contextlib.contextmanager
def maintained_time():
    ct = cmds.currentTime(query=True)
    try:
        yield
    finally:
        cmds.currentTime(ct, edit=True)


def memodict(f):
    """Memoization decorator for a function taking a single argument.

    See: http://code.activestate.com/recipes/
         578231-probably-the-fastest-memoization-decorator-in-the-/
    """

    class memodict(dict):
        def __missing__(self, key):
            ret = self[key] = f(key)
            return ret

    return memodict().__getitem__


def get_visible_in_frame_range(nodes, start, end):
    """Return nodes that are visible in start-end frame range.

    - Ignores intermediateObjects completely.
    - Considers animated visibility attributes + upstream visibilities.

    This is optimized for large scenes where some nodes in the parent
    hierarchy might have some input connections to the visibilities,
    e.g. key, driven keys, connections to other attributes, etc.

    This only does a single time step to `start` if current frame is
    not inside frame range since the assumption is made that changing
    a frame isn't so slow that it beats querying all visibility
    plugs through MDGContext on another frame.

    Args:
        nodes (list): List of node names to consider.
        start (int): Start frame.
        end (int): End frame.

    Returns:
        list: List of node names. These will be long full path names so
            might have a longer name than the input nodes.

    """
    # States we consider per node
    VISIBLE = 1  # always visible
    INVISIBLE = 0  # always invisible
    ANIMATED = -1  # animated visibility

    # Ensure integers
    start = int(start)
    end = int(end)

    # Consider only non-intermediate dag nodes and use the "long" names.
    nodes = cmds.ls(nodes, long=True, noIntermediate=True, type="dagNode")
    if not nodes:
        return []

    with maintained_time():
        # Go to first frame of the range if we current time is outside of
        # the queried range. This is to do a single query on which are at
        # least visible at a time inside the range, (e.g those that are
        # always visible)
        current_time = cmds.currentTime(query=True)
        if not (start <= current_time <= end):
            cmds.currentTime(start)

        visible = cmds.ls(nodes, long=True, visible=True)
        if len(visible) == len(nodes) or start == end:
            # All are visible on frame one, so they are at least visible once
            # inside the frame range.
            return visible

    # For the invisible ones check whether its visibility and/or
    # any of its parents visibility attributes are animated. If so, it might
    # get visible on other frames in the range.
    @memodict
    def get_state(node):
        plug = node + ".visibility"
        connections = cmds.listConnections(plug,
                                           source=True,
                                           destination=False)
        if connections:
            return ANIMATED
        else:
            return VISIBLE if cmds.getAttr(plug) else INVISIBLE

    visible = set(visible)
    invisible = [node for node in nodes if node not in visible]
    always_invisible = set()
    # Iterate over the nodes by short to long names, so we iterate the highest
    # in hierarcy nodes first. So the collected data can be used from the
    # cache for parent queries in next iterations.
    node_dependencies = dict()
    for node in sorted(invisible, key=len):

        state = get_state(node)
        if state == INVISIBLE:
            always_invisible.add(node)
            continue

        # If not always invisible by itself we should go through and check
        # the parents to see if any of them are always invisible. For those
        # that are "ANIMATED" we consider that this node is dependent on
        # that attribute, we store them as dependency.
        dependencies = set()
        if state == ANIMATED:
            dependencies.add(node)

        traversed_parents = list()
        for parent in iter_parents(node):

            if not parent:
                # Workaround bug in iter_parents
                continue

            if parent in always_invisible or get_state(parent) == INVISIBLE:
                # When parent is always invisible then consider this parent,
                # this node we started from and any of the parents we
                # have traversed in-between to be *always invisible*
                always_invisible.add(parent)
                always_invisible.add(node)
                always_invisible.update(traversed_parents)
                break

            # If we have traversed the parent before and its visibility
            # was dependent on animated visibilities then we can just extend
            # its dependencies for to those for this node and break further
            # iteration upwards.
            parent_dependencies = node_dependencies.get(parent, None)
            if parent_dependencies is not None:
                dependencies.update(parent_dependencies)
                break

            state = get_state(parent)
            if state == ANIMATED:
                dependencies.add(parent)

            traversed_parents.append(parent)

        if node not in always_invisible and dependencies:
            node_dependencies[node] = dependencies

    if not node_dependencies:
        return list(visible)

    # Now we only have to check the visibilities for nodes that have animated
    # visibility dependencies upstream. The fastest way to check these
    # visibility attributes across different frames is with Python api 2.0
    # so we do that.
    @memodict
    def get_visibility_mplug(node):
        """Return api 2.0 MPlug with cached memoize decorator"""
        sel = om.MSelectionList()
        sel.add(node)
        dag = sel.getDagPath(0)
        return om.MFnDagNode(dag).findPlug("visibility", True)

    # We skip the first frame as we already used that frame to check for
    # overall visibilities. And end+1 to include the end frame.
    scene_units = om.MTime.uiUnit()
    for frame in range(start + 1, end + 1):

        mtime = om.MTime(frame, unit=scene_units)
        context = om.MDGContext(mtime)

        # Build little cache so we don't query the same MPlug's value
        # again if it was checked on this frame and also is a dependency
        # for another node
        frame_visibilities = {}

        for node, dependencies in node_dependencies.items():

            for dependency in dependencies:

                dependency_visible = frame_visibilities.get(dependency, None)
                if dependency_visible is None:
                    mplug = get_visibility_mplug(dependency)
                    dependency_visible = mplug.asBool(context)
                    frame_visibilities[dependency] = dependency_visible

                if not dependency_visible:
                    # One dependency is not visible, thus the
                    # node is not visible.
                    break

            else:
                # All dependencies are visible.
                visible.add(node)
                # Remove node with dependencies for next iterations
                # because it was visible at least once.
                node_dependencies.pop(node)

        # If no more nodes to process break the frame iterations..
        if not node_dependencies:
            break

    return list(visible)
