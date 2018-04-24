from avalon import api


def get_reference_node_parents(ref):
    """Return all parent reference nodes of reference node

    Args:
        ref (str): reference node.

    Returns:
        list: The upstream parent reference nodes.

    """
    from maya import cmds

    parent = cmds.referenceQuery(ref,
                                 referenceNode=True,
                                 parent=True)
    parents = []
    while parent:
        parents.append(parent)
        parent = cmds.referenceQuery(parent,
                                     referenceNode=True,
                                     parent=True)
    return parents


class ReferenceLoader(api.Loader):
    """A basic ReferenceLoader for Maya

    This will implement the basic behavior for a loader to inherit from that
    will containerize the reference and will implement the `remove` and
    `update` logic.

    """
    def load(self,
             context,
             name=None,
             namespace=None,
             data=None):

        import os
        from avalon.maya import lib
        from avalon.maya.pipeline import containerise

        assert os.path.exists(self.fname), "%s does not exist." % self.fname

        asset = context['asset']

        namespace = namespace or lib.unique_namespace(
            asset["name"] + "_",
            prefix="_" if asset["name"][0].isdigit() else "",
            suffix="_",
        )

        self.process_reference(context=context,
                               name=name,
                               namespace=namespace,
                               data=data)

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

    def process_reference(self, context, name, namespace, data):
        """To be implemented by subclass"""
        raise NotImplementedError("Must be implemented by subclass")

    def _get_reference_node(self, members):
        """Get the reference node from the container members

        Returns:
            str: Reference node name.

        """

        from maya import cmds

        # Collect the references without .placeHolderList[] attributes as
        # unique entries (objects only) and skipping the sharedReferenceNode.
        references = set()
        for ref in cmds.ls(members, exactType="reference", objectsOnly=True):

            # Ignore `sharedReferenceNode`
            if ref == "sharedReferenceNode":
                continue

            references.add(ref)

        assert references, "No reference node found in container"

        # Get highest reference node (least parents)
        highest = min(references,
                      key=lambda x: len(get_reference_node_parents(x)))

        # Warn the user when we're taking the highest reference node
        if len(references) > 1:
            self.log.warning("More than one reference node found in "
                             "container, using highest reference node: "
                             "%s (in: %s)", highest, list(references))

        return highest

    def update(self, container, representation):

        import os
        from maya import cmds

        node = container["objectName"]

        path = api.get_representation_path(representation)

        # Get reference node from container members
        members = cmds.sets(node, query=True, nodesOnly=True)
        reference_node = self._get_reference_node(members)

        file_type = {
            "ma": "mayaAscii",
            "mb": "mayaBinary",
            "abc": "Alembic"
        }.get(representation["name"])

        assert file_type, "Unsupported representation: %s" % representation

        assert os.path.exists(path), "%s does not exist." % path

        try:
            content = cmds.file(path,
                                loadReference=reference_node,
                                type=file_type,
                                returnNewNodes=True)
        except RuntimeError as exc:
            # When changing a reference to a file that has load errors the
            # command will raise an error even if the file is still loaded
            # correctly (e.g. when raising errors on Arnold attributes)
            # When the file is loaded and has content, we consider it's fine.
            if not cmds.referenceQuery(reference_node, isLoaded=True):
                raise

            content = cmds.referenceQuery(reference_node,
                                          nodes=True,
                                          dagPath=True)
            if not content:
                raise

            self.log.warning("Ignoring file read error:\n%s", exc)

        # Fix PLN-40 for older containers created with Avalon that had the
        # `.verticesOnlySet` set to True.
        if cmds.getAttr(node + ".verticesOnlySet"):
            self.log.info("Setting %s.verticesOnlySet to False", node)
            cmds.setAttr(node + ".verticesOnlySet", False)

        # Add new nodes of the reference to the container
        cmds.sets(content, forceElement=node)

        # Remove any placeHolderList attribute entries from the set that
        # are remaining from nodes being removed from the referenced file.
        members = cmds.sets(node, query=True)
        invalid = [x for x in members if ".placeHolderList" in x]
        if invalid:
            cmds.sets(invalid, remove=node)

        # Update metadata
        cmds.setAttr(node + ".representation",
                     str(representation["_id"]),
                     type="string")

    def remove(self, container):
        """Remove an existing `container` from Maya scene

        Deprecated; this functionality is replaced by `api.remove()`

        Arguments:
            container (avalon-core:container-1.0): Which container
                to remove from scene.

        """

        from maya import cmds

        node = container["objectName"]

        # Assume asset has been referenced
        members = cmds.sets(node, query=True)
        reference_node = self._get_reference_node(members)

        assert reference_node, ("Imported container not supported; "
                                "container must be referenced.")

        self.log.info("Removing '%s' from Maya.." % container["name"])

        namespace = cmds.referenceQuery(reference_node, namespace=True)
        fname = cmds.referenceQuery(reference_node, filename=True)
        cmds.file(fname, removeReference=True)

        try:
            cmds.delete(node)
        except ValueError:
            # Already implicitly deleted by Maya upon removing reference
            pass

        try:
            # If container is not automatically cleaned up by May (issue #118)
            cmds.namespace(removeNamespace=namespace,
                           deleteNamespaceContent=True)
        except RuntimeError:
            pass
