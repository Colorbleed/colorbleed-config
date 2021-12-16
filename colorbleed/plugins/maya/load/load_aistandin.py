import os
from avalon import api, io

# TODO aiVolume doesn't automatically set velocity fps correctly, set manual?


class LoadAiStandin(api.Loader):
    """Load AiStandin"""

    families = ["colorbleed.pointcache", "colorbleed.model", "ass"]
    representations = ["abc", "ass", "usd", "usdc", "usda"]

    label = "Load as Arnold StandIn"
    order = -2
    icon = "code-fork"
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

        asset_name = context['asset']["name"]
        namespace = namespace or lib.unique_namespace(
            asset_name + "_",
            prefix="_" if asset_name[0].isdigit() else "",
            suffix="_",
        )

        # Root group
        label = "{}:{}".format(namespace, name)

        # Create transform with shape
        transform_name = label + "_aiStandIn"
        transform = cmds.createNode("transform", name=transform_name)
        standin = cmds.createNode("aiStandIn",
                                  name="{}Shape".format(transform_name),
                                  parent=transform)

        self._apply_settings(standin,
                             path=self.fname)

        cmds.lockNode(standin, lock=True)

        nodes = [transform, standin]
        self[:] = nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__)

    def _apply_settings(self,
                        standin,
                        path):
        """Apply the settings for the VDB path to the VRayVolumeGrid"""
        from maya import cmds

        # The path is either a single file or sequence in a folder.
        is_single_file = os.path.isfile(path)
        if is_single_file:
            filename = path
        else:
            # The path points to the publish sequence folder so we
            # find the first file in there.
            files = sorted(os.listdir(path))
            first = next((x for x in files), None)
            if first is None:
                raise RuntimeError("Couldn't find first .vdb file of "
                                   "sequence in: %s" % path)
            filename = os.path.join(path, first)

        # Tell the standin whether it should load as sequence or single file
        cmds.setAttr(standin + ".useFrameExtension", not is_single_file)

        # Set file path
        cmds.setAttr(standin + ".dso", filename, type="string")

    def update(self, container, representation):

        import maya.cmds as cmds

        path = api.get_representation_path(representation)

        # Find VRayVolumeGrid
        members = cmds.sets(container['objectName'], query=True)
        standin = cmds.ls(members, type="aiStandIn", long=True)
        assert len(standin) == 1, "This is a bug"

        # Update the VRayVolumeGrid
        self._apply_settings(standin[0],
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
