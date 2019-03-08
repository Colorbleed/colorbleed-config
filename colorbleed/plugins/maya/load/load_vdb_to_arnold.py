import os
from avalon import api, io

# TODO aiVolume doesn't automatically set velocity fps correctly, set manual?


class LoadVDBtoArnold(api.Loader):
    """Load OpenVDB for Arnold in aiVolume"""

    families = ["colorbleed.vdbcache"]
    representations = ["vdb"]

    label = "Load VDB to Arnold"
    order = -8
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
        if not cmds.pluginInfo("mtoa", query=True, loaded=True):
            cmds.loadPlugin("mtoa")

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
        grid_node = cmds.createNode("aiVolume",
                                    name="{}Shape".format(root),
                                    parent=root)

        self._apply_settings(grid_node,
                             path=self.fname)

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
        cmds.setAttr(grid_node + ".filename", filename, type="string")

    def update(self, container, representation):

        import maya.cmds as cmds

        path = api.get_representation_path(representation)

        # Find VRayVolumeGrid
        members = cmds.sets(container['objectName'], query=True)
        grid_nodes = cmds.ls(members, type="aiVolume", long=True)
        assert len(grid_nodes) == 1, "This is a bug"

        # Update the VRayVolumeGrid
        self._apply_settings(grid_nodes[0],
                             path=path)

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
