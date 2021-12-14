from maya import cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.action


class ValidateNodeNoGhosting(pyblish.api.InstancePlugin):
    """Ensure nodes do not have ghosting enabled.

    If one would publish towards a non-Maya format it's likely that stats
    like ghosting won't be exported, eg. exporting to Alembic.

    Instead of creating many micro-managing checks (like this one) to ensure
    attributes have not been changed from their default it could be more
    efficient to export to a format that will never hold such data anyway.

    """

    order = colorbleed.api.ValidateContentsOrder
    hosts = ['maya']
    families = ['colorbleed.model', 'colorbleed.rig']
    label = "No Ghosting"
    actions = [colorbleed.maya.action.SelectInvalidAction]

    _attributes = {'ghosting': 0}

    @classmethod
    def get_invalid(cls, instance):

        # Transforms and shapes seem to have ghosting
        nodes = cmds.ls(instance, long=True, type=['transform', 'shape'])
        invalid = []
        for node in nodes:
            for attr, required_value in cls._attributes.items():
                if cmds.attributeQuery(attr, node=node, exists=True):

                    value = cmds.getAttr('{0}.{1}'.format(node, attr))
                    if value != required_value:
                        invalid.append(node)

        return invalid

    def process(self, instance):

        invalid = self.get_invalid(instance)

        if invalid:
            raise ValueError("Nodes with ghosting enabled found: "
                             "{0}".format(invalid))
