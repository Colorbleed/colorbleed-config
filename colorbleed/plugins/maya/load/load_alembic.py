import colorbleed.maya.plugin


class AbcLoader(colorbleed.maya.plugin.ReferenceLoader):
    """Reference Alembic"""

    families = ["colorbleed.animation",
                "colorbleed.pointcache",
                "colorbleed.model"]
    label = "Reference Alembic"
    representations = ["abc"]
    order = -10
    icon = "code-fork"
    color = "orange"

    def process_reference(self, context, name, namespace, data):

        import maya.cmds as cmds

        cmds.loadPlugin("AbcImport.mll", quiet=True)
        nodes = cmds.file(self.fname,
                          namespace=namespace,
                          sharedReferenceFile=False,
                          groupReference=True,
                          groupName="{}:{}".format(namespace, name),
                          reference=True,
                          returnNewNodes=True)

        self[:] = nodes

        return nodes
