from avalon import api

from avalon.houdini import pipeline, lib


class FbxLoader(api.Loader):
    """Load FBX"""
    # todo: Like SideFX Labs FBX Archive add attributes for import options

    families = ["colorbleed.fbx"]
    label = "Load FBX"
    representations = ["fbx"]
    order = -10
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, data=None):

        import os
        import hou

        # Format file name, Houdini only wants forward slashes
        file_path = os.path.normpath(self.fname)
        file_path = file_path.replace("\\", "/")

        # Get the root node
        obj = hou.node("/obj")

        # Define node name
        namespace = namespace if namespace else context["asset"]["name"]
        node_name = "{}_{}".format(namespace, name) if namespace else name

        # Create a new geo node
        fbx = hou.hipFile.importFBX(file_path)[0]
        fbx.setName(node_name, unique_name=True)

        nodes = [fbx]
        self[:] = nodes

        return pipeline.containerise(node_name,
                                     namespace,
                                     nodes,
                                     context,
                                     self.__class__.__name__,
                                     suffix="")

    def update(self, container, representation):

        import hou

        node = container["node"]

        # Update the file path
        file_path = api.get_representation_path(representation)
        file_path = file_path.replace("\\", "/")

        new_fbx = hou.hipFile.importFBX(file_path)[0]

        # Delete the old contents
        for child in node.children():
            child.destroy()

        # Copy the new contents
        new_children = new_fbx.children()
        for child in new_children:
            child.copyTo(node)

        # Destroy the new FBX container
        new_fbx.destroy()

        # Update attribute
        node.setParms({"representation": str(representation["_id"])})

    def remove(self, container):

        node = container["node"]
        node.destroy()
