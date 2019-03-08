import os
from avalon import api, io


class LoadVDBtoRedShift(api.Loader):
    """Load OpenVDB in a Redshift Volume Shape

    Note that the RedshiftVolumeShape is created without a RedshiftVolume
    shader assigned. To get the Redshift volume to render correctly assign
    a RedshiftVolume shader (in the Hypershade) and set the density, scatter
    and emission channels to the channel names of the volumes in the VDB file.

    """

    families = ["colorbleed.vdbcache"]
    representations = ["vdb"]

    label = "Load VDB to RedShift"
    order = -9
    icon = "cloud"
    color = "orange"

    def load(self, context, name=None, namespace=None, data=None):

        from maya import cmds
        import avalon.maya.lib as lib
        from avalon.maya.pipeline import containerise

        assert os.path.exists(self.fname), (
                "Path does not exist: %s" % self.fname
        )

        # Check if the plugin for redshift is available on the pc
        try:
            cmds.loadPlugin("redshift4maya", quiet=True)
        except Exception as exc:
            self.log.error("Encountered exception:\n%s" % exc)
            return

        # Check if viewport drawing engine is Open GL Core (compat)
        render_engine = None
        compatible = "OpenGL"
        if cmds.optionVar(exists="vp2RenderingEngine"):
            render_engine = cmds.optionVar(query="vp2RenderingEngine")

        if not render_engine or not render_engine.startswith(compatible):
            raise RuntimeError("Current scene's settings are incompatible."
                               "See Preferences > Display > Viewport 2.0 to "
                               "set the render engine to '%s<type>'"
                               % compatible)

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

        # Create VR
        volume_node = cmds.createNode("RedshiftVolumeShape",
                                      name="{}Shape".format(root),
                                      parent=root)

        self._apply_settings(volume_node, path=self.fname)

        nodes = [root, volume_node]
        self[:] = nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__)

    def _apply_settings(self,
                        grid_node,
                        path):
        """Apply the settings for the VDB path to the VRayVolumeGrid"""
        from maya import cmds

        # The path is either a single file or sequence in a folder.
        is_single_file = os.path.isfile(path)
        if is_single_file:
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

        # Tell Redshift whether it should load as sequence or single file
        cmds.setAttr(grid_node + ".useFrameExtension", not is_single_file)

        # Set file path
        cmds.setAttr(grid_node + ".fileName", filename, type="string")

    def update(self, container, representation):

        import maya.cmds as cmds

        path = api.get_representation_path(representation)

        # Find VRayVolumeGrid
        members = cmds.sets(container['objectName'], query=True)
        grid_nodes = cmds.ls(members, type="RedshiftVolumeShape", long=True)
        assert len(grid_nodes) == 1, "This is a bug"

        # Update the VRayVolumeGrid
        self._apply_settings(grid_nodes[0], path=path)

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

