import os
import json
import contextlib

from maya import cmds
import maya.mel as mel

import pyblish.api
import avalon.maya

import colorbleed.api


def bake_to_layer(nodes, layer_name, start, end,
                  disable_implicit_control=True):
    """Bake to new animation layer

    Args:
        disable_implicit_control (bool): Whether to
            disable implicit controls (e.g. IK Handles)
            after the bake.

    Returns:
        str: Name of created animLayer

    """
    before = set(cmds.ls(exactType="container"))

    # Bake
    result = cmds.bakeResults(
        nodes,
        shape=False,
        controlPoints=False,
        simulation=True,
        t=(start, end),
        sampleBy=1,
        oversamplingRate=1,
        disableImplicitControl=disable_implicit_control,
        preserveOutsideKeys=False,
        sparseAnimCurveBake=True,
        removeBakedAttributeFromLayer=False,
        bakeOnOverrideLayer=True,
        minimizeRotation=True
    )

    if not result:
        raise RuntimeError("Nothing baked.")

    # Get the new container
    after = cmds.ls(exactType="container")
    new = [x for x in after if x not in before]
    assert len(new) == 1, "Must be a single new container for bake results"
    container = new[0]

    # Get animLayer
    members = cmds.container(container, query=True, nodeList=True)
    layer = cmds.ls(members, type="animLayer")[0]

    # Rename the layer
    return cmds.rename(layer, layer_name)


@contextlib.contextmanager
def undo_changes():
    """Undos whatever was done during the context"""
    chunk_name = "<temporary undo>"
    cmds.undoInfo(openChunk=True, chunkName=chunk_name)
    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)
        if cmds.undoInfo(query=True, undoName=True) == chunk_name:
            cmds.undo()


@contextlib.contextmanager
def ogs_paused():
    before = cmds.ogs(query=True, pause=True)
    if not before:
        cmds.ogs(pause=True)
    try:
        yield
    finally:
        current = cmds.ogs(query=True, pause=True)
        if current != before:
            cmds.ogs(pause=True)


def layerbake(nodes, settings):
    """Helper function to bake specific frame ranges to separate layers.

    Note: This is based on the guide for baking the animation layers to
          Lens Studio for Snapchat filters.

    - Each animLayer will be shifted to start at frame zero.
    - Each animLayer will have its keys reduced (optimization for filesize)

    Examples:
        # Bake pCube1's animation to an intro and outro animLayer.
        layerbake(nodes=["pCube1"],
                  settings=[("intro", 1, 10),
                            ("outro", 20, 30)])

    Args:
        nodes (list): List of Maya nodes.
        settings (list): List of 3-tuples containing "name", "start" and "end"

    Returns:
        list: The created animLayer nodes.

    """
    # Validate inputs
    assert isinstance(settings, list)
    for entry in settings:
        assert isinstance(entry, (tuple, list))
        assert len(entry) == 3

    # Bake the layers by name, start and end frame.
    created = []
    for i, (name, start, end) in enumerate(settings):

        # Workaround (Hack):
        # Only disable the implicit controls
        # once we reach the last layer to bake
        # so that up to that point the IK handles
        # bake as they should behave
        disable_implicit = i == len(settings) - 1

        layer = bake_to_layer(nodes, name, start, end,
                              disable_implicit_control=disable_implicit)
        print("Baked to: %s (%s - %s)" % (layer, start, end))
        created.append(layer)

        # Mute the layer temporarily so that it doesn't mess
        # up the next layer bake
        cmds.animLayer(layer, edit=True, mute=True)

    for layer in created:

        # Unmute the layers
        cmds.animLayer(layer, edit=True, mute=False)
        curves = cmds.animLayer(layer, query=True, animCurves=True)
        start = min(cmds.keyframe(curves, query=True, tc=True))

        # Shift all keys in layers to start at frame zero
        if start != 0:
            cmds.keyframe(curves, edit=True, timeChange=-start, relative=True)

        # Force simplication of keys to reduce datasize
        cmds.filterCurve(curves,
                         filter="keyReducer",
                         selectedKeys=False,
                         precisionMode=0,
                         precision=0.001)

    return created


def set_fbx_export_clips(clips):
    """Set the FBX Export Split Animation Takes for next export"""
    # Clear any existing clip list set in the FBX Exporter
    mel.eval("FBXExportSplitAnimationIntoTakes -clear")
    # Remove explicit Maya default Take001 from export
    mel.eval("FBXExportDeleteOriginalTakeOnSplitAnimation  -v true")
    for name, start, end in clips:
        # Escape quotation marks if in clip name
        name = name.replace('"', r'\"')

        mel.eval("FBXExportSplitAnimationIntoTakes -v "
                 "\"{0}\" {1} {2}".format(name, start, end))


def get_time_slider_clips():
    """Return current time slider bookmarks as clips.

    The clips are 3-tuples: name, start, end.

    Returns:
        list: Clips sorted by start time.

    """

    bookmarks = cmds.ls(type="timeSliderBookmark")
    result = []
    for bookmark in bookmarks:
        name = cmds.getAttr(bookmark + ".name")
        start = cmds.getAttr(bookmark + ".timeRangeStart")
        end = cmds.getAttr(bookmark + ".timeRangeStop") - 1
        result.append((name, start, end))

    return sorted(result, key=lambda x: x[1])


class ExtractFBX(colorbleed.api.Extractor):
    """Extract FBX from Maya.

    This extracts reproducible FBX exports ignoring any of the settings set
    on the local machine in the FBX export options window.

    All export settings are applied with the `FBXExport*` commands prior
    to the `FBXExport` call itself. The options can be overridden with their
    nice names as seen in the "options" property on this class.

    For more information on FBX exports see:
    - https://knowledge.autodesk.com/support/maya/learn-explore/caas
    /CloudHelp/cloudhelp/2016/ENU/Maya/files/GUID-6CCE943A-2ED4-4CEE-96D4
    -9CB19C28F4E0-htm.html
    - http://forums.cgsociety.org/archive/index.php?t-1032853.html
    - https://groups.google.com/forum/#!msg/python_inside_maya/cLkaSo361oE
    /LKs9hakE28kJ

    """

    order = pyblish.api.ExtractorOrder
    label = "Extract FBX"
    families = ["colorbleed.fbx"]

    @property
    def options(self):
        """Overridable options for FBX Export

        Given in the following format
            - {NAME: EXPECTED TYPE}

        If the overridden option's type does not match,
        the option is not included and a warning is logged.

        """

        return {
            "cameras": bool,
            "smoothingGroups": bool,
            "hardEdges": bool,
            "tangents": bool,
            "smoothMesh": bool,
            "instances": bool,
            # "referencedContainersContent": bool, # deprecated in Maya 2016+
            "applyConstantKeyReducer": bool,
            "bakeComplexAnimation": int,
            "bakeComplexStart": int,
            "bakeComplexEnd": int,
            "bakeComplexStep": int,
            "bakeResampleAnimation": bool,
            "animationOnly": bool,
            "useSceneName": bool,
            "quaternion": str,  # "euler"
            "shapes": bool,     # blendShape
            "skins": bool,
            "skeletonDefinitions": bool,
            "constraints": bool,
            "lights": bool,
            "embeddedTextures": bool,
            "inputConnections": bool,
            "upAxis": str,  # x, y or z,
            "triangulate": bool,
            "scaleFactor": float
        }

    @property
    def default_options(self):
        """The default options for FBX extraction.

        This includes shapes, skins, constraints, lights and incoming
        connections and exports with the Y-axis as up-axis.

        By default this uses the time sliders start and end time.

        """

        start_frame = int(cmds.playbackOptions(query=True,
                                               animationStartTime=True))
        end_frame = int(cmds.playbackOptions(query=True,
                                             animationEndTime=True))

        return {
            "cameras": False,
            "smoothingGroups": False,
            "hardEdges": False,
            "tangents": False,
            "smoothMesh": False,
            "instances": False,
            "applyConstantKeyReducer": False,
            "bakeComplexAnimation": True,
            "bakeComplexStart": start_frame,
            "bakeComplexEnd": end_frame,
            "bakeComplexStep": 1,
            "bakeResampleAnimation": True,
            "animationOnly": False,
            "useSceneName": False,
            "quaternion": "euler",
            "shapes": True,
            "skins": True,
            "skeletonDefinitions": False,
            "constraints": False,
            "lights": True,
            "embeddedTextures": True,
            "inputConnections": False,
            "upAxis": "y",
            "triangulate": False,
            "scaleFactor": 1.0
        }

    def parse_overrides(self, instance, options):
        """Inspect data of instance to determine overridden options

        An instance may supply any of the overridable options
        as data, the option is then added to the extraction.

        """

        for key in instance.data:
            if key not in self.options:
                continue

            # Ensure the data is of correct type
            value = instance.data[key]
            if not isinstance(value, self.options[key]):
                self.log.warning(
                    "Overridden attribute {key} was of "
                    "the wrong type: {invalid_type} "
                    "- should have been {valid_type}".format(
                        key=key,
                        invalid_type=type(value).__name__,
                        valid_type=self.options[key].__name__))
                continue

            options[key] = value

        return options

    def process(self, instance):

        # Ensure FBX plug-in is loaded
        cmds.loadPlugin("fbxmaya", quiet=True)

        # Define output path
        directory = self.staging_dir(instance)
        filename = "{0}.fbx".format(instance.name)
        path = os.path.join(directory, filename)

        # The export requires forward slashes because we need
        # to format it into a string in a mel expression
        path = path.replace('\\', '/')

        self.log.info("Extracting FBX to: {0}".format(path))

        members = instance.data["setMembers"]
        self.log.info("Members: {0}".format(members))
        self.log.info("Instance: {0}".format(instance[:]))

        # Parse export options
        options = self.default_options
        options = self.parse_overrides(instance, options)
        self.log.info("Export options: {0}".format(options))

        # Collect the start and end including handles
        start = instance.data["startFrame"]
        end = instance.data["endFrame"]
        handles = instance.data.get("handles", 0)
        if handles:
            start -= handles
            end += handles

        options['bakeComplexStart'] = start
        options['bakeComplexEnd'] = end

        # First apply the default export settings to be fully consistent
        # each time for successive publishes
        mel.eval("FBXResetExport")

        bake_anim_layers = instance.data.get("bakeAnimLayers")
        if bake_anim_layers:
            # If there are custom bake ranges then we don't let the FBX
            # exporter perform baking too
            options["bakeComplexAnimation"] = False
            options["bakeResampleAnimation"] = True
            options["applyConstantKeyReducer"] = True

        # Set animation clips from Timeline Bookmarks if enabled
        use_bookmarks = instance.data.get("useTimelineBookmarksAsTakes")
        if use_bookmarks:
            clips = get_time_slider_clips()
            set_fbx_export_clips(clips)

        # Apply the FBX overrides through MEL since the commands
        # only work correctly in MEL according to online
        # available discussions on the topic
        for option, value in options.items():
            key = option[0].upper() + option[1:]  # uppercase first letter

            # Boolean must be passed as lower-case strings
            # as to MEL standards
            if isinstance(value, bool):
                value = str(value).lower()

            template = "FBXExport{0} -v {1}"
            if key in {"UpAxis", "ScaleFactor"}:
                template = "FBXExport{0} {1}"

            cmd = template.format(key, value)
            self.log.info(cmd)
            mel.eval(cmd)

        # Never show the UI or generate a log
        mel.eval("FBXExportShowUI -v false")
        mel.eval("FBXExportGenerateLog -v false")

        # Export
        with avalon.maya.maintained_selection():

            # todo(roy): Cleanup this code to have less code duplication
            #            and branching
            if bake_anim_layers:
                # Special FBX Export with baked animation layers
                self.log.debug("Baking animation layers: %s" %
                               bake_anim_layers)
                settings = json.loads(bake_anim_layers)

                with ogs_paused():
                    with undo_changes():
                        layerbake(members, settings)

                        # FBX Export
                        cmds.select(members, r=1, noExpand=True)
                        mel.eval('FBXExport -f "{}" -s'.format(path))

            else:
                # FBX Export
                cmds.select(members, r=1, noExpand=True)
                mel.eval('FBXExport -f "{}" -s'.format(path))

        if "files" not in instance.data:
            instance.data["files"] = list()

        instance.data["files"].append(filename)

        self.log.info("Extract FBX successful to: {0}".format(path))
