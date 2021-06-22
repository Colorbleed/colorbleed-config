from avalon import api


class SetDressLoader(api.Loader):

    families = ["colorbleed.setdress"]
    representations = ["json"]

    label = "Load Set Dress"
    order = -9
    icon = "code-fork"
    color = "orange"

    def load(self, context, name, namespace, data):

        from avalon.maya.pipeline import containerise
        from avalon.maya import lib

        asset = context['asset']['name']
        namespace = namespace or lib.unique_namespace(
            asset + "_",
            prefix="_" if asset[0].isdigit() else "",
            suffix="_",
        )

        from colorbleed.maya import api_setdress

        containers = api_setdress.load_package(filepath=self.fname,
                                               name=name,
                                               namespace=namespace)

        self[:] = containers

        # Only containerize if any nodes were loaded by the Loader
        nodes = self[:]
        if not nodes:
            return

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__)

    def update(self, container, representation):

        from colorbleed.maya import api_setdress
        return api_setdress.update_package(container,
                                           representation)

    def remove(self, container):
        """Remove all sub containers"""

        from avalon import api
        from colorbleed.maya import api_setdress
        import maya.cmds as cmds

        # Remove all members
        member_containers = api_setdress.get_contained_containers(container)
        for member_container in member_containers:
            self.log.info("Removing container %s",
                          member_container['objectName'])
            api.remove(member_container)

        # Remove alembic hierarchy reference
        # TODO: Check whether removing all contained references is safe enough
        members = cmds.sets(container['objectName'], query=True) or []
        references = cmds.ls(members, type="reference")
        for reference in references:
            self.log.info("Removing %s", reference)
            fname = cmds.referenceQuery(reference, filename=True)
            cmds.file(fname, removeReference=True)

        # Delete container and its contents
        if cmds.objExists(container['objectName']):
            members = cmds.sets(container['objectName'], query=True) or []
            cmds.delete([container['objectName']] + members)

        # TODO: Ensure namespace is gone