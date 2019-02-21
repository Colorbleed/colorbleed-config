import colorbleed.maya.plugin


class LookLoader(colorbleed.maya.plugin.ReferenceLoader):
    """Reference look .ma file without assigning shaders."""

    families = ["colorbleed.look"]
    representations = ["ma"]

    label = "Reference look"
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
                              returnNewNodes=True)

        self[:] = nodes

    def switch(self, container, representation):
        self.update(container, representation)
