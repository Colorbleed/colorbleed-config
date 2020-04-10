from avalon import api


class MultiverseUSDLoader(api.Loader):
    """Load Multiverse USD Compound"""

    families = ["colorbleed.usd",
                "colorbleed.pointcache",
                "colorbleed.animation",
                "colorbleed.model"]
    representations = ["usd", "usda", "usdc", "abc"]

    label = "Import USD (Multiverse)"
    order = -5
    icon = "code-fork"
    color = "orange"

    def load(self, context, name, namespace, data):

        import multiverse
        import maya.cmds as cmds
        import avalon.maya.lib as lib
        from avalon.maya.pipeline import containerise
        from colorbleed.maya.lib import namespaced

        asset = context['asset']['name']
        namespace = namespace or lib.unique_namespace(
            asset + "_",
            prefix="_" if asset[0].isdigit() else "",
            suffix="_",
        )

        cmds.loadPlugin("MultiverseForMaya", quiet=True)

        cmds.namespace(add=namespace)
        with namespaced(namespace, new=False):

            shape = multiverse.CreateUsdCompound(self.fname)
            shape = cmds.rename(shape, name+"Shape")
            transform = cmds.listRelatives(shape, parent=True, fullPath=True)
            transform = cmds.rename(transform, name)
            shape = cmds.listRelatives(transform, fullPath=True)[0]

        # Lock shape node so it can't be deleted or reparented
        cmds.lockNode(shape, lock=True)

        nodes = [transform, shape]
        self[:] = nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__)

    def update(self, container, representation):

        import maya.cmds as cmds
        import multiverse

        path = api.get_representation_path(representation)

        # Update the cache
        members = cmds.sets(container['objectName'], query=True)
        caches = cmds.ls(members, type="mvUsdCompoundShape", long=True)

        assert len(caches) == 1, "This is a bug"

        for cache in caches:
            multiverse.SetUsdCompoundAssetPaths(cache, [path])

        cmds.setAttr(container["objectName"] + ".representation",
                     str(representation["_id"]),
                     type="string")

    def switch(self, container, representation):
        self.update(container, representation)

    def remove(self, container):
        import maya.cmds as cmds
        members = cmds.sets(container['objectName'], query=True)
        cmds.lockNode(members, lock=False)
        cmds.delete([container['objectName']] + members)

        # Clean up the namespace
        try:
            cmds.namespace(removeNamespace=container['namespace'],
                           deleteNamespaceContent=True)
        except RuntimeError:
            pass
