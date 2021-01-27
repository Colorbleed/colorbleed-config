import os
from avalon import api, io
from maya import cmds

# List of 3rd Party Channels Mapping names for VRayVolumeGrid
# See: https://docs.chaosgroup.com/display/VRAY4MAYA/Input
#      #Input-3rdPartyChannelsMapping
THIRD_PARTY_CHANNELS = {
    2: "Smoke",
    1: "Temperature",
    10: "Fuel",
    4: "Velocity.x",
    5: "Velocity.y",
    6: "Velocity.z",
    7: "Red",
    8: "Green",
    9: "Blue",
    14: "Wavelet Energy",
    19: "Wavelet.u",
    20: "Wavelet.v",
    21: "Wavelet.w",
    # These are not in UI or documentation but V-Ray does seem to set these.
    15: "AdvectionOrigin.x",
    16: "AdvectionOrigin.y",
    17: "AdvectionOrigin.z",

}


def _fix_duplicate_vvg_callbacks():
    """Workaround to kill duplicate VRayVolumeGrids attribute callbacks.

    This fixes a huge lag in Maya on switching 3rd Party Channels Mappings
    or to different .vdb file paths because it spams an attribute changed
    callback: `vvgUserChannelMappingsUpdateUI`.

    ChaosGroup bug ticket: 154-008-9890

    Found with:
        - Maya 2019.2 on Windows 10
        - V-Ray: V-Ray Next for Maya, update 1 version 4.12.01.00001

    """

    jobs = cmds.scriptJob(listJobs=True)

    matched = set()
    for entry in jobs:
        # Remove the number
        index, callback = entry.split(":", 1)
        callback = callback.strip()

        # Detect whether it is a `vvgUserChannelMappingsUpdateUI`
        # attribute change callback
        if callback.startswith('"-runOnce" 1 "-attributeChange" "'):
            if '"vvgUserChannelMappingsUpdateUI(' in callback:
                if callback in matched:
                    # If we've seen this callback before then
                    # delete the duplicate callback
                    cmds.scriptJob(kill=int(index))
                else:
                    matched.add(callback)


class LoadVDBtoVRay(api.Loader):
    """Load OpenVDB for V-Ray in VRayVolumeGrid"""

    families = ["colorbleed.vdbcache"]
    representations = ["vdb"]

    label = "Load VDB to VRay"
    order = -10
    icon = "cloud"
    color = "orange"

    def load(self, context, name, namespace, data):

        import avalon.maya.lib as lib
        from avalon.maya.pipeline import containerise

        assert os.path.exists(self.fname), (
                "Path does not exist: %s" % self.fname
        )

        # Ensure V-ray is loaded
        if not cmds.pluginInfo("vrayformaya", query=True, loaded=True):
            cmds.loadPlugin("vrayformaya")

        # When V-Ray version 4+ (V-Ray Next) then ensure the separate
        # "vrayvolumegrid" plug-in gets loaded too.
        if cmds.pluginInfo("vrayformaya", query=True, version=True) == "Next":
            if not cmds.pluginInfo("vrayvolumegrid", query=True, loaded=True):
                cmds.loadPlugin("vrayvolumegrid")

        # Check if viewport drawing engine is Open GL Core (compat)
        render_engine = None
        compatible = "OpenGLCoreProfileCompat"
        if cmds.optionVar(exists="vp2RenderingEngine"):
            render_engine = cmds.optionVar(query="vp2RenderingEngine")

        if not render_engine or render_engine != compatible:
            raise RuntimeError("Current scene's settings are incompatible."
                               "See Preferences > Display > Viewport 2.0 to "
                               "set the render engine to '%s'" % compatible)

        asset = context['asset']

        asset_name = asset["name"]
        namespace = namespace or lib.unique_namespace(
            asset_name + "_",
            prefix="_" if asset_name[0].isdigit() else "",
            suffix="_",
        )

        # Root group
        label = "{}:{}".format(namespace, name)
        root = cmds.group(name=label, empty=True)

        # Create VRayVolumeGrid
        grid_node = cmds.createNode("VRayVolumeGrid",
                                    name="{}Shape".format(root),
                                    parent=root)

        self._apply_settings(grid_node,
                             path=self.fname,
                             show_preset_popup=True)

        nodes = [root, grid_node]
        self[:] = nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__)

    def _apply_settings(self,
                        grid_node,
                        path,
                        show_preset_popup=True):
        """Apply the settings for the VDB path to the VRayVolumeGrid"""

        from colorbleed.maya.lib import attribute_values
        from maya import cmds

        # The path is either a single file or sequence in a folder.
        if os.path.isfile(path):
            filename = path

        else:
            # The path points to the publish .vdb sequence folder so we
            # find the first file in there that ends with .vdb
            files = sorted(x for x in os.listdir(path) if x.endswith(".vdb"))
            if not files:
                raise RuntimeError("Couldn't find .vdb files in: %s" % path)

            if len(files) == 1:
                # Ensure check for single file is also done in folder
                fname = files[0]
            else:
                # Sequence
                from avalon.vendor import clique
                # todo: check support for negative frames as input
                collections, remainder = clique.assemble(files)
                assert len(collections) == 1, (
                    "Must find a single image sequence, "
                    "found: %s" % (collections,)
                )
                fname = collections[0].format('{head}{padding}{tail}')

            filename = os.path.join(path, fname)

        # Suppress preset pop-up if we want.
        popup_attr = "{0}.inDontOfferPresets".format(grid_node)
        popup = {popup_attr: not show_preset_popup}

        # Even when not applying a preset V-Ray will reset the 3rd Party
        # Channels Mapping of the VRayVolumeGrid when setting the .inPath
        # value. As such we try and preserve the values ourselves.
        # Reported as ChaosGroup bug ticket: 154-011-2909 
        # todo(roy): Remove when new V-Ray release preserves values
        user_mapping = cmds.getAttr(grid_node + ".usrchmap") or ""

        # Fix lag on change, see function docstring
        # todo(roy): Remove when new V-Ray release fixes duplicate calls
        _fix_duplicate_vvg_callbacks()

        with attribute_values(popup):
            cmds.setAttr(grid_node + ".inPath", filename, type="string")

        # Reapply the 3rd Party channels user mapping when we the user was
        # was not shown a popup
        if not show_preset_popup:
            channels = cmds.getAttr(grid_node + ".usrchmapallch").split(";")
            channels = set(channels)  # optimize lookup
            restored_mapping = ""
            for entry in user_mapping.split(";"):
                if not entry:
                    # Ignore empty entries
                    continue

                # If 3rd Party Channels selection channel still exists then
                # add it again.
                index, channel = entry.split(",")
                attr = THIRD_PARTY_CHANNELS.get(int(index),
                                                # Fallback for when a mapping
                                                # was set that is not in the
                                                # documentation
                                                "???")
                if channel in channels:
                    restored_mapping += entry + ";"
                else:
                    self.log.warning("Can't preserve '%s' mapping due to "
                                     "missing channel '%s' on node: "
                                     "%s" % (attr, channel, grid_node))

            if not show_preset_popup and restored_mapping:
                cmds.setAttr(grid_node + ".usrchmap",
                             restored_mapping,
                             type="string")

    def update(self, container, representation):

        import maya.cmds as cmds

        path = api.get_representation_path(representation)

        # Find VRayVolumeGrid
        members = cmds.sets(container['objectName'], query=True)
        grid_nodes = cmds.ls(members, type="VRayVolumeGrid", long=True)
        assert len(grid_nodes) == 1, "This is a bug"

        # Update the VRayVolumeGrid
        self._apply_settings(grid_nodes[0],
                             path=path,
                             show_preset_popup=False)

        # Update container representation
        cmds.setAttr(container["objectName"] + ".representation",
                     str(representation["_id"]),
                     type="string")

    def switch(self, container, representation):
        self.update(container, representation)

    def remove(self, container):
        import maya.cmds as cmds

        # Get all members of the avalon container, ensure they are unlocked
        # and delete everything
        members = cmds.sets(container['objectName'], query=True)
        cmds.lockNode(members, lock=False)
        cmds.delete([container['objectName']] + members)

        # Clean up the namespace
        try:
            cmds.namespace(removeNamespace=container['namespace'],
                           deleteNamespaceContent=True)
        except RuntimeError:
            pass
