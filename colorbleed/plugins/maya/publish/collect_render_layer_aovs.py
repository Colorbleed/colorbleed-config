from maya import cmds
from maya import mel

import pyblish.api

import colorbleed.maya.lib as lib


def get_arnold_light_groups():
    # reference: {arnold}\scripts\mtoa\ui\ae\aiAOVTemplate.py
    # loop over all light groups in the scene
    lights = cmds.ls(exactType=['pointLight',
                                'directionalLight',
                                'spotLight',
                                'areaLight',
                                'aiAreaLight',
                                'aiSkyDomeLight',
                                'aiMeshLight',
                                'aiPhotometricLight'])

    existing_groups = set()
    for light in lights:
        light_group = cmds.getAttr(light + ".aiAov")
        if light_group:
            existing_groups.add(light_group)

    return sorted(list(existing_groups))


def get_redshift_light_groups():
    return sorted(mel.eval("redshiftAllAovLightGroups"))


class CollectRenderLayerAOVS(pyblish.api.InstancePlugin):
    """Collect all render layer's AOVs / Render Elements that will render.

    This collector is important to be able to Extend Frames.

    Technical information:
    Each renderer uses different logic to work with render passes.
    VRay - RenderElement
        Simple node connection to the actual renderLayer node

    Arnold - AOV:
        Uses its own render settings node and connects an aiOAV to it

    Redshift - AOV:
        Uses its own render settings node and RedshiftAOV node. It is not
        connected but all AOVs are enabled for all render layers by default.

    Requires:
        instance    -> renderer
        instance    -> setMembers
        instance    -> subset

    Provides:
        instance    -> renderPasses

    """

    order = pyblish.api.CollectorOrder + 0.01
    label = "Render Elements / AOVs"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer"]

    def process(self, instance):

        # Get renderer
        renderer = instance.data["renderer"]

        rp_node_types = {
            "vray": ["VRayRenderElement", "VRayRenderElementSet"],
            "arnold": ["aiAOV"],
            "redshift": ["RedshiftAOV"]
        }

        if renderer not in rp_node_types.keys():
            self.log.error("Unsupported renderer found: '{}'".format(renderer))
            return

        result = []

        # Collect all AOVs / Render Elements
        layer = instance.data["setMembers"]
        layer_name = instance.data["subset"]
        node_type = rp_node_types[renderer]
        render_elements = cmds.ls(type=node_type)

        # Check if AOVs / Render Elements are enabled
        for element in render_elements:
            enabled = lib.get_attr_in_layer("{}.enabled".format(element),
                                            layer=layer)
            if not enabled:
                continue

            pass_name = self.get_pass_name(renderer, element, instance)
            if isinstance(pass_name, (tuple, list)):
                # Single AOV generates multiple output passes
                result.extend(pass_name)
            else:
                # Single AOV generates single output (most often)
                result.append(pass_name)

        self.log.debug("Found {} AOVs for "
                       "'{}': {}".format(len(result),
                                         instance.data["subset"],
                                         sorted(result)))

        instance.data["renderPasses"] = result

    def get_pass_name(self, renderer, node, instance):

        if renderer == "vray":

            vray_class_type = cmds.getAttr(node + ".vrayClassType")
            if vray_class_type == "velocityChannel":
                # Somehow later versions of V-Ray don't have vray_name
                # attributes for velocity passes. So we rely on
                # vray_filename_velocity
                return cmds.getAttr(node + ".vray_filename_velocity")

            # Get render element pass type
            vray_node_attr = next((attr for attr in cmds.listAttr(node)
                                   if attr.startswith("vray_name")), None)
            if vray_node_attr is None:
                raise RuntimeError("Failed to retrieve vray_name "
                                   "attribute for: %s" % node)
            pass_type = vray_node_attr.rsplit("_", 1)[-1]

            # Support V-Ray extratex explicit name (if set by user)
            if pass_type == "extratex":

                explicit_attr = "{}.vray_explicit_name_extratex".format(node)
                explicit_name = cmds.getAttr(explicit_attr)
                if explicit_name:
                    return explicit_name

                # Somehow V-Ray appends the Texture node's name to the filename
                texture_attr = node + ".vray_texture_extratex"
                connected_texture = cmds.listConnections(texture_attr,
                                                         source=True,
                                                         destination=False)
                if connected_texture:
                    basename = cmds.getAttr("{}.{}".format(node,
                                                           vray_node_attr))
                    return "{}_{}".format(basename, connected_texture[0])

            # Node type is in the attribute name but we need to check if value
            # of the attribute as it can be changed
            return cmds.getAttr("{}.{}".format(node, vray_node_attr))

        elif renderer == "arnold":
            name = cmds.getAttr("{}.name".format(node))

            # RGBA pass renders as 'beauty'
            if name == "RGBA":
                name = "beauty"

            # Support light Groups
            all_light_groups = cmds.getAttr("{}.lightGroups".format(node))
            light_groups = []
            if all_light_groups:
                # All light groups is enabled
                light_groups = get_arnold_light_groups()
            else:
                value = cmds.getAttr("{}.lightGroupsList".format(node))
                selected_light_groups = value.strip().split()
                light_groups = selected_light_groups

            if light_groups:
                return ["{}_{}".format(name, light_group) for light_group in
                        light_groups]

            return name
        elif renderer == "redshift":
            name = cmds.getAttr("{}.name".format(node))

            aov = cmds.getAttr(node + ".aovType")
            if aov == "Beauty":
                # Redshift skips rendering of masterlayer without AOV suffix
                # when a Beauty AOV is rendered. It overrides the main layer.
                instance.data["renderNoMasterLayer"] = True

            if cmds.getAttr("{}.supportsLightGroups".format(node)):

                # Support light Groups
                all_light_groups = cmds.getAttr(
                    "{}.allLightGroups".format(node)
                )
                light_groups = []
                if all_light_groups:
                    # All light groups is enabled
                    light_groups = get_redshift_light_groups()
                else:
                    value = cmds.getAttr("{}.lightGroupList".format(node))
                    # note: string value can return None when never set
                    if value:
                        selected_light_groups = value.strip().split()
                        light_groups = selected_light_groups

                if light_groups:
                    names = ["{}_{}".format(name, light_group) for
                             light_group in light_groups]

                    # Redshift AOV Light Select always renders the global AOV
                    names.append(name)

                    return names

            return name
        else:
            raise RuntimeError("Unsupported renderer: '{}'".format(renderer))
