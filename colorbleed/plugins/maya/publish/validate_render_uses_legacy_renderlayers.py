import maya.cmds as cmds

import pyblish.api
import colorbleed.api


class ValidateRenderUsesLegacyRenderlayers(pyblish.api.InstancePlugin):
    """Ensure Render Setup is enabled for Deadline when it's currently enabled.

    This validates that Deadline's `UseLegacyRenderLayers` is set to match
    with the current state of the Maya session. So that when currently
    legacy renderlayers are enabled it is set to True and if currently
    Render Setup is used then `UseLegacyRenderLayers` must be False.

    """

    order = pyblish.api.ValidatorOrder
    label = "Render Uses Legacy Renderlayers"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer"]
    actions = [colorbleed.api.RepairAction]

    def process(self, instance):

        render_globals = instance.data.get("renderGlobals", {})
        use_legacy_render_layers = render_globals.get("UseLegacyRenderLayers",
                                                      True)

        maya_uses_legacy_render_layers = not cmds.mayaHasRenderSetup()

        if maya_uses_legacy_render_layers != use_legacy_render_layers:
            raise ValueError("Use legacy renderlayers setting is different "
                             "from what your current Maya session is using.")

    @classmethod
    def repair(cls, instance):
        """Set the required filename prefix"""

        node = cmds.ls("renderglobalsDefault")[0]
        maya_uses_legacy_render_layers = not cmds.mayaHasRenderSetup()
        cmds.setAttr(node + ".useLegacyRenderLayers",
                     maya_uses_legacy_render_layers)

