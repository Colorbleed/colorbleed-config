from maya import cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.lib as lib


class ValidateMeshSingleUVSet(pyblish.api.InstancePlugin):
    """Warn on multiple UV sets existing for each polygon mesh.

    On versions prior to Maya 2017 this will force no multiple uv sets because
    the Alembic exports in Maya prior to 2017 don't support writing multiple
    UV sets.

    """

    order = colorbleed.api.ValidateMeshOrder
    hosts = ['maya']
    families = ['colorbleed.model', 'colorbleed.pointcache']
    category = 'uv'
    optional = True
    version = (0, 1, 0)
    label = "Mesh Single UV Set"
    actions = [colorbleed.api.SelectInvalidAction,
               colorbleed.api.RepairAction]

    @staticmethod
    def get_invalid(instance):

        meshes = cmds.ls(instance, type='mesh', long=True)

        invalid = []
        for mesh in meshes:
            uvSets = cmds.polyUVSet(mesh,
                                    query=True,
                                    allUVSets=True) or []

            # ensure unique (sometimes maya will list 'map1' twice)
            uvSets = set(uvSets)

            if len(uvSets) != 1:
                invalid.append(mesh)

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance 'objectSet'"""

        invalid = self.get_invalid(instance)

        if invalid:

            message = "Nodes found with multiple UV sets: {0}".format(invalid)

            # Maya 2017 and up allows multiple UV sets in Alembic exports
            # so we allow it, yet just warn the user to ensure they know about
            # the other UV sets.
            allowed = int(cmds.about(version=True)) >= 2017

            if allowed:
                self.log.warning(message)
            else:
                raise ValueError(message)

    @classmethod
    def repair(cls, instance):
        for mesh in cls.get_invalid(instance):
            lib.remove_other_uv_sets(mesh)
