from maya import cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.action
import colorbleed.maya.lib as lib


class ValidateMeshColorSets(pyblish.api.InstancePlugin):
    """Shows warning when mesh has color sets but publishing has been disabled.

    This will only show a WARNING when Color Sets are excluded from publish.

    Model publish instances have a toggle to enable 'writeColorSets'.
    When disabled but the meshes have color sets
    this validator will warn the user that the color sets will be excluded
    from the output. This doesn't have to be an issue so it's up to the user
    whether they are fine with it - so just a warning is shown.

    """

    order = colorbleed.api.ValidateMeshOrder
    families = ['colorbleed.model']
    hosts = ['maya']
    label = 'Mesh Color Sets'
    actions = [colorbleed.maya.action.SelectInvalidAction]

    @classmethod
    def get_invalid(cls, instance):

        invalid =[]

        meshes = cmds.ls(instance, type='mesh', long=True)
        for mesh in meshes:
            sets = cmds.polyColorSet(mesh, query=True, allColorSets=True)
            if sets:
                invalid.append(mesh)

        return invalid

    def process(self, instance):
        """Process all meshes"""

        if instance.data.get("writeColorSets", False):
            self.log.debug("Skipping check because color sets are "
                           "enabled to be extracted with the mesh.")
            return

        invalid = self.get_invalid(instance)
        if invalid:
            self.log.warning("Meshes have color sets but color sets are "
                             "excluded from extraction: {}".format(invalid))
