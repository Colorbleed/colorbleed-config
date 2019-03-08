import os
from avalon import api, io


class LoadVDBtoVRay(api.Loader):
    """Load OpenVDB for V-Ray in VRayVolumeGrid"""

    families = ["colorbleed.vdbcache"]
    representations = ["vdb"]

    label = "Load VDB to VRay"
    order = -10
    icon = "cloud"
    color = "orange"

    def load(self, context, name, namespace, data):

        from maya import cmds
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
            files = sorted(os.listdir(path))
            first = next((x for x in files if x.endswith(".vdb")), None)
            if first is None:
                raise RuntimeError("Couldn't find first .vdb file of "
                                   "sequence in: %s" % path)
            filename = os.path.join(path, first)

        # Suppress preset pop-up if we want.
        popup_attr = "{0}.inDontOfferPresets".format(grid_node)
        popup = {popup_attr: not show_preset_popup}

        with attribute_values(popup):
            cmds.setAttr(grid_node + ".inPath", filename, type="string")

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
