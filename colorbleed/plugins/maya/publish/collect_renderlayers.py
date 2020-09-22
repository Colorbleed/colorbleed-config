import copy
from maya import cmds

import pyblish.api

from avalon import maya, api
import colorbleed.maya.lib as lib


class CollectMayaRenderlayers(pyblish.api.ContextPlugin):
    """Gather instances by active render layers

    Whenever a renderlayer has multiple renderable cameras then each
    camera will get its own instance. As such, the amount of instances
    will be "renderable cameras (in layer) x layers".

    """

    order = pyblish.api.CollectorOrder
    hosts = ["maya"]
    label = "Render Layers"

    def process(self, context):

        asset = api.Session["AVALON_ASSET"]
        filepath = context.data["currentFile"].replace("\\", "/")

        # Get render globals node
        try:
            render_globals = cmds.ls("renderglobalsDefault")[0]
        except IndexError:
            self.log.info("Skipping renderlayer collection, no "
                          "renderGlobalsDefault found..")
            return

        # Get all valid renderlayers
        # This is how Maya populates the renderlayer display
        rlm_attribute = "renderLayerManager.renderLayerId"
        connected_layers = cmds.listConnections(rlm_attribute) or []
        valid_layers = set(connected_layers)

        # Get all renderlayers and check their state
        renderlayers = [i for i in cmds.ls(type="renderLayer") if
                        cmds.getAttr("{}.renderable".format(i)) and not
                        cmds.referenceQuery(i, isNodeReferenced=True)]

        # Sort by displayOrder
        def sort_by_display_order(layer):
            return cmds.getAttr("%s.displayOrder" % layer)

        renderlayers = sorted(renderlayers, key=sort_by_display_order)

        for layer in renderlayers:

            # Check if layer is in valid (linked) layers
            if layer not in valid_layers:
                self.log.warning("%s is invalid, skipping" % layer)
                continue

            if layer.endswith("defaultRenderLayer"):
                layername = "masterLayer"
            else:
                if layer.startswith("rs_"):
                    # todo: make sure it is a Render Setup layer
                    # Remove Maya render setup prefix `rs_`
                    layername = layer[3:]
                else:
                    layername = layer

            # Get layer specific settings, might be overrides
            data = {
                "setMembers": layer,
                "publish": True,
                "startFrame": self.get_render_attribute("startFrame",
                                                        layer=layer),
                "endFrame": self.get_render_attribute("endFrame",
                                                      layer=layer),
                "byFrameStep": self.get_render_attribute("byFrameStep",
                                                         layer=layer),
                "renderer": self.get_render_attribute("currentRenderer",
                                                      layer=layer),

                # instance subset
                "family": "colorbleed.renderlayer",
                "families": ["colorbleed.renderlayer"],
                "asset": asset,
                "time": api.time(),
                "author": context.data["user"],

                # Add source to allow tracing back to the scene from
                # which was submitted originally
                "source": filepath
            }

            # Include the renderer in the families so we can direct specific
            # validators to specific renderers.
            renderer_family = "colorbleed.renderlayer.%s" % data["renderer"]
            data["families"].append(renderer_family)

            # Apply each user defined attribute as data
            for attr in cmds.listAttr(layer, userDefined=True) or list():
                try:
                    value = cmds.getAttr("{}.{}".format(layer, attr))
                except Exception:
                    # Some attributes cannot be read directly,
                    # such as mesh and color attributes. These
                    # are considered non-essential to this
                    # particular publishing pipeline.
                    value = None

                data[attr] = value

            # Include (optional) global settings
            # todo: Take into account layer overrides
            # Get global overrides and translate to Deadline values
            overrides = self.parse_options(render_globals)
            data.update(**overrides)

            # Collect renderable cameras and create an instance
            # per camera per renderlayer.
            renderable = [c for c in cmds.ls(type="camera", long=True) if
                          lib.get_attr_in_layer("%s.renderable" % c,
                                                layer=layer)]
            if not renderable:
                self.log.warning("No renderable camera in renderlayer: %s, "
                                 "skipped collecting.." % layer)

            # Keep track of the amount of all renderable cameras in the
            # layer so we can use this information elsewhere, however note
            # that we split instances per camera below as `data["camera"]`
            data["cameras"] = renderable

            for camera in renderable:

                # Define nice label
                label = "{0} ({1})".format(layername, data["asset"])
                if len(renderable) > 1:
                    # If more than one camera, include camera name in label
                    name = cmds.ls(cmds.listRelatives(camera,
                                                      parent=True,
                                                      fullPath=True))[0]
                    label += " - {0}".format(name)

                    # Prefix the camera before the layername
                    nice_name = name.replace(":", "_").replace("|", "_")
                    subset = "{0}_{1}".format(nice_name, layername)
                    self.log.info(subset)
                else:
                    subset = layername

                # Always end with start frame and end frame in label
                label += "  [{0}-{1}]".format(int(data["startFrame"]),
                                              int(data["endFrame"]))

                instance = context.create_instance(layername)
                instance.data["subset"] = subset
                instance.data["label"] = label
                instance.data["camera"] = camera
                instance.data["layername"] = layername
                instance.data.update(data)

    def get_render_attribute(self, attr, layer):
        return lib.get_attr_in_layer("defaultRenderGlobals.{}".format(attr),
                                     layer=layer)

    def parse_options(self, render_globals):
        """Get all overrides with a value, skip those without

        Here's the kicker. These globals override defaults in the submission
        integrator, but an empty value means no overriding is made.
        Otherwise, Frames would override the default frames set under globals.

        Args:
            render_globals (str): collection of render globals

        Returns:
            dict: only overrides with values
        """

        attributes = maya.read(render_globals)

        options = {"renderGlobals": {}}
        options["renderGlobals"]["Priority"] = attributes["priority"]

        # Check for specific pools
        pool_a, pool_b = self._discover_pools(attributes)
        options["renderGlobals"].update({"Pool": pool_a})
        if pool_b:
            options["renderGlobals"].update({"SecondaryPool": pool_b})

        legacy = attributes["useLegacyRenderLayers"]
        options["renderGlobals"]["UseLegacyRenderLayers"] = legacy

        # Machine list
        machine_list = attributes["machineList"]
        if machine_list:
            key = "Whitelist" if attributes["whitelist"] else "Blacklist"
            options['renderGlobals'][key] = machine_list

        # Suspend publish job
        state = "Suspended" if attributes["suspendPublishJob"] else "Active"
        options["publishJobState"] = state

        chunksize = attributes.get("framesPerTask", 1)
        options["renderGlobals"]["ChunkSize"] = chunksize

        # Override frames should be False if extendFrames is False. This is
        # to ensure it doesn't go off doing crazy unpredictable things
        override_frames = False
        extend_frames = attributes.get("extendFrames", False)
        if extend_frames:
            override_frames = attributes.get("overrideExistingFrame", False)

        options["extendFrames"] = extend_frames
        options["overrideExistingFrame"] = override_frames

        maya_render_plugin = "MayaBatch"
        if not attributes.get("useMayaBatch", True):
            maya_render_plugin = "MayaCmd"

        options["mayaRenderPlugin"] = maya_render_plugin

        return options

    def _discover_pools(self, attributes):

        pool_a = None
        pool_b = None

        # Check for specific pools
        if "primaryPool" in attributes:
            pool_a = attributes["primaryPool"]
            pool_b = attributes["secondaryPool"]

        else:
            # Backwards compatibility
            pool_str = attributes.get("pools", None)
            if pool_str:
                pool_a, pool_b = pool_str.split(";")

        # Ensure empty entry token is caught
        if pool_b == "-":
            pool_b = None

        return pool_a, pool_b
