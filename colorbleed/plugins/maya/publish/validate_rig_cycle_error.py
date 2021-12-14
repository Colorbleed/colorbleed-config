from maya import cmds

import pyblish.api

from avalon import maya

import colorbleed.api
import colorbleed.maya.action
from colorbleed.maya.lib import undo_chunk


class ValidateRigCycleError(pyblish.api.InstancePlugin):
    """Validate rig nodes produce have no cycle errors."""

    order = colorbleed.api.ValidateContentsOrder + 0.05
    label = "Rig Cycle Errors"
    hosts = ["maya"]
    families = ["colorbleed.rig"]
    actions = [colorbleed.maya.action.SelectInvalidAction]
    optional = True

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Rig nodes produce a cycle error: %s" % invalid)

    @classmethod
    def get_invalid(cls, instance):

        nodes = instance[:]
        with maya.maintained_selection():
            cmds.select(nodes, noExpand=True)
            plugs = cmds.cycleCheck(all=False,  # check selection only,
                                    list=True)
            invalid = cmds.ls(plugs, objectsOnly=True, long=True)
            return invalid

