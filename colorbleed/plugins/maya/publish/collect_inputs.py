import copy
from maya import cmds

from colorbleed.maya import lib

import avalon.io as io
import avalon.api as api
import pyblish.api


def collect_input_containers(containers, nodes):
    """Collect containers that contain any of the node in `nodes`.

    This will return any loaded Avalon container that contains at least one of
    the nodes. As such, the Avalon container is an input for it. Or in short,
    there are member nodes of that container.

    Returns:
        list: Input avalon containers

    """

    # Instead of querying all members of each set and then doing a
    # lookup for many nodes we just check for destination connections
    # to sets with which we assume membership. This makes the query
    # much faster for large scenes.
    connected_sets = set(cmds.listConnections(nodes,
                                              source=False,
                                              destination=True,
                                              plugs=False,
                                              connections=False,
                                              t="objectSet",
                                              exactType=True) or [])

    containers_with_members = []
    for container in containers:
        node = container["objectName"]
        if node in connected_sets:
            containers_with_members.append(container)

    return containers_with_members


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

        # For large scenes the querying of "host.ls()" can be relatively slow
        # e.g. up to a second. As such for many instances all calling it could
        # easily add a slow Collector. As such, we cache out the so we
        # trigger it only once.
        # todo(roy): Instead of hidden cache make "CollectContainers" plug-in
        cache_key = "__cache_containers"
        scene_containers = instance.context.data.get(cache_key, None)
        if scene_containers is None:
            # Query the scenes' containers if there's no cache yet
            host = api.registered_host()
            scene_containers = list(host.ls())
            instance.context.data["__cache_containers"] = scene_containers

        # Collect the relevant input containers for this instance
        if "colorbleed.renderlayer" in set(instance.data.get("families", [])):
            # Special behavior for renderlayers
            self.log.debug("Collecting renderlayer inputs....")
            containers = self._collect_renderlayer_inputs(scene_containers,
                                                          instance)

        else:
            # Basic behavior
            nodes = instance[:]

            # Collect containers for the given set of nodes
            containers = collect_input_containers(scene_containers,
                                                  nodes)

        inputs = [c["representation"] for c in containers]
        instance.data["inputs"] = inputs

        self.log.info("Collected inputs: %s" % inputs)

    def _collect_renderlayer_inputs(self, scene_containers, instance):
        """Collects inputs from nodes in renderlayer, incl. shaders + camera"""

        # Get the renderlayer
        renderlayer = instance.data.get("setMembers")

        if renderlayer == "defaultRenderLayer":
            # Assume all loaded containers in the scene are inputs
            # for the masterlayer
            return copy.deepcopy(scene_containers)
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

            containers = collect_input_containers(scene_containers, members)

        return containers


