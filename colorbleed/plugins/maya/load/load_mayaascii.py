import colorbleed.maya.plugin


class MayaAsciiLoader(colorbleed.maya.plugin.ReferenceLoader):
    """Load the model"""

    families = ["colorbleed.mayaAscii"]
    representations = ["ma"]

    label = "Reference Maya Ascii"
    order = -10
    icon = "code-fork"
    color = "orange"

    def process_reference(self, context, name, namespace, data):

        import maya.cmds as cmds
        from avalon import maya

        with maya.maintained_selection():
            nodes = cmds.file(self.fname,
                              namespace=namespace,
                              reference=True,
                              returnNewNodes=True,
                              groupReference=True,
                              groupName="{}:{}".format(namespace, name))

        self[:] = nodes

        return nodes
