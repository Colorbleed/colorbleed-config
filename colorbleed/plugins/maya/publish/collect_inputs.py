from maya import cmds

from colorbleed.maya import lib

import avalon.io as io
import avalon.api as api
import pyblish.api


def collect_input_containers(nodes):
    """Collect containers that contain any of the node in `nodes`.

    This will return any loaded Avalon container that contains at least one of
    the nodes. As such, the Avalon container is an input for it. Or in short,
    there are member nodes of that container.

    Returns:
        list: Input avalon containers

    """

    # Lookup by node ids
    lookup = frozenset(cmds.ls(nodes, uuid=True))

    containers = []
    host = api.registered_host()
    for container in host.ls():
        node = container["objectName"]
        members = cmds.sets(node, query=True)
        members_uuid = cmds.ls(members, uuid=True)

        # If there's an intersection
        if not lookup.isdisjoint(members_uuid):
            containers.append(container)

    return containers


class CollectUpstreamInputs(pyblish.api.InstancePlugin):
    """Collect input source inputs for this publish.

    This will include `inputs` data of which loaded publishes were used in the
    generation of this publish. This leaves an upstream trace to what was used
    as input.

    """

    label = "Collect Inputs"
    order = pyblish.api.CollectorOrder + 0.2
    hosts = ["maya"]

    def process(self, instance):

        if "colorbleed.renderlayer" in set(instance.data.get("families", [])):
            # Special behavior for renderlayers
            self.log.debug("Collecting renderlayer inputs....")
            containers = self._collect_renderlayer_inputs(instance)

        else:
            # Basic behavior
            nodes = instance[:]

            # Collect containers for the given set of nodes
            containers = collect_input_containers(nodes)

        inputs = [c["representation"] for c in containers]
        instance.data["inputs"] = inputs

        self.log.info("Collected inputs: %s" % inputs)

    def _collect_renderlayer_inputs(self, instance):
        """Collects inputs from nodes in renderlayer, incl. shaders + camera"""

        # Get the renderlayer
        renderlayer = instance.data.get("setMembers")

        if renderlayer == "defaultRenderLayer":
            # Assume all loaded containers in the scene are inputs
            # for the masterlayer
            host = api.registered_host()
            containers = list(host.ls())
        else:
            # Get the members of the layer
            members = cmds.editRenderLayerMembers(renderlayer,
                                                  query=True,
                                                  fullNames=True) or []
                                                  
            # In some cases invalid objects are returned from
            # `editRenderLayerMembers` so we filter them out
            members = cmds.ls(members, long=True)

            # Include all children
            children = cmds.listRelatives(members,
                                          allDescendents=True,
                                          fullPath=True) or []
            members.extend(children)

            # Include assigned shaders in renderlayer
            shapes = cmds.ls(members, shapes=True, long=True)
            shaders = set()
            for shape in shapes:
                shape_shaders = lib.get_shader_in_layer(shape,
                                                        layer=renderlayer)
                shaders.update(shape_shaders)
            members.extend(shaders)

            # Explicitly include the camera being rendered in renderlayer
            cameras = instance.data.get("cameras")
            members.extend(cameras)

            containers = collect_input_containers(members)

        return containers


