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


def set_namespace(node, namespace):
    """Add node to the namespace"""
    from maya import cmds

    name = node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
    cmds.rename(node, namespace + ":" + name)


def get_namespace(node):
    """Return namespace from node name"""
    return node.rsplit("|", 1)[-1].rsplit(":", 1)[0]


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

        nodes = self[:]
        nodes = self._get_containerizable_nodes(nodes)

        # Only containerize if any nodes were loaded by the Loader
        if not nodes:
            return

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__)

    def _get_containerizable_nodes(self, nodes):
        """Filter to only the nodes we want to include in the container"""
        if not nodes:
            # Do nothing if empty list
            return nodes
        
        # Containerize only the Reference node
        return [self._get_reference_node(nodes)]

    def process_reference(self, context, name, namespace, data):
        """To be implemented by subclass"""
        raise NotImplementedError("Must be implemented by subclass")

    def _get_reference_node(self, members):
        """Get the reference node from the container members
        Args:
            members: list of node names

        Returns:
            str: Reference node name.

        """

        from maya import cmds

        # Collect the references without .placeHolderList[] attributes as
        # unique entries (objects only) and skipping the sharedReferenceNode.
        references = set()
        for ref in cmds.ls(members, exactType="reference", objectsOnly=True):

            # Ignore any `:sharedReferenceNode`
            if ref.rsplit(":", 1)[-1].startswith("sharedReferenceNode"):
                continue

            # Ignore _UNKNOWN_REF_NODE_ (PLN-160)
            if ref.rsplit(":", 1)[-1].startswith("_UNKNOWN_REF_NODE_"):
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
            "abc": "Alembic",
            "fbx": "FBX"
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
            
        # Ensure reference node is included in the returned content
        # because cmds.file(returnNewNodes=True) doesn't return it since
        # the reference node already existed. Similarly cmds.referenceQuery
        # doesn't return it either. So for updating we can safely return it.
        content.append(reference_node)

        # Fix PLN-40 for older containers created with Avalon that had the
        # `.verticesOnlySet` set to True.
        if cmds.getAttr("{}.verticesOnlySet".format(node)):
            self.log.info("Setting %s.verticesOnlySet to False", node)
            cmds.setAttr("{}.verticesOnlySet".format(node), False)

        # Add new nodes of the reference to the container
        content = self._get_containerizable_nodes(content)
        if content:
            cmds.sets(content, forceElement=node)

        # Remove any placeHolderList attribute entries from the set that
        # are remaining from nodes being removed from the referenced file.
        members = cmds.sets(node, query=True)
        invalid = [x for x in members if ".placeHolderList" in x]
        if invalid:
            cmds.sets(invalid, remove=node)

        # Update metadata
        cmds.setAttr("{}.representation".format(node),
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

    def switch(self, container, representation):
        self.update(container, representation)

        from avalon import pipeline
        import avalon.maya.lib as lib
        from maya import cmds

        # Define namespace similar to how the default loader does it on load
        # but using the new representation so we can update the namespace
        context = pipeline.get_representation_context(representation)
        asset = context['asset']
        namespace = lib.unique_namespace(
            asset["name"] + "_",
            prefix="_" if asset["name"][0].isdigit() else "",
            suffix="_",
        )

        # Update the namespace, this requires the reference to be loaded
        # But since we update the first it will always be loaded.
        node = container["objectName"]
        members = cmds.sets(node, query=True)
        reference_node = self._get_reference_node(members)
        assert reference_node, ("Imported container not supported; "
                                "container must be referenced.")
        fname = cmds.referenceQuery(reference_node, filename=True)
        cmds.file(fname, edit=True, namespace=namespace)

        # Workaround: Maya doesn't automatically rename the Reference Group
        # and Locator namespace so let's do that manually.
        associated_nodes = self._get_associated_nodes(reference_node)
        old_namespaces = set()
        for node in associated_nodes:
            old_namespaces.add(get_namespace(node))
            set_namespace(node, namespace)

        # Also rename the actual name of the group node
        def _get_group(nodes):
            """Assume group is the one without shape nodes"""
            groups = [n for n in nodes if
                      not cmds.listRelatives(n, shapes=True)]
            if len(groups) > 1:
                raise RuntimeError(
                    "More than a single reference node group found: %s" %
                    groups)
            if groups:
                return groups[0]

        associated_nodes = self._get_associated_nodes(reference_node)
        group_node = _get_group(associated_nodes)
        if group_node:
            new_group_name = context["subset"]["name"]
            cmds.rename(group_node, namespace + ":" + new_group_name)

        # Delete old namespaces of associated nodes when empty now
        for old_namespace in old_namespaces:
            is_empty = not cmds.namespaceInfo(old_namespace,
                                              listNamespace=True)
            if is_empty:
                cmds.namespace(removeNamespace=old_namespace)

    def _get_associated_nodes(self, reference_node):
        from maya import cmds

        return cmds.listConnections(reference_node + ".associatedNode[0]",
                                    source=True,
                                    destination=True) or []
