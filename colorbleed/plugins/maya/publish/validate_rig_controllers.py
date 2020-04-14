from maya import cmds

import pyblish.api

import colorbleed.api
import colorbleed.maya.action
from colorbleed.maya.lib import undo_chunk


def get_controls(instance):
    """Return the controls from the controls_SET of the rig instance"""

    sets = cmds.ls(instance, type="objectSet", long=True)
    controllers_sets = [i for i in sets if i == "controls_SET"]
    controls = cmds.ls(cmds.sets(controllers_sets, query=True), long=True)
    assert controls, "Must have 'controls_SET' in rig instance"

    return controls


class ValidateRigControlsVisibilityAttribute(pyblish.api.InstancePlugin):
    """Validate rig controller visibility attribute is locked.

    The visibility attribute must be locked.

    """
    order = colorbleed.api.ValidateContentsOrder + 0.05
    label = "Rig Controls Visibility"
    hosts = ["maya"]
    families = ["colorbleed.rig"]
    actions = [colorbleed.api.RepairAction,
               colorbleed.maya.action.SelectInvalidAction]

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Controls have unlocked visibility "
                               "attribute: %s" % invalid)

    @classmethod
    def get_invalid(cls, instance):

        invalid = []
        for control in get_controls(instance):

            attribute = "{}.visibility".format(control)
            locked = cmds.getAttr(attribute, lock=True)
            if not locked:
                invalid.append(control)

        return invalid

    @classmethod
    def repair(cls, instance):

        invalid = cls.get_invalid(instance)
        if not invalid:
            return

        with undo_chunk():
            for control in invalid:
                attribute = "{}.visibility".format(control)
                cls.log.info("Locking attribute: %s" % attribute)
                cmds.setAttr(attribute, lock=True)


class ValidateRigControlsNoConnections(pyblish.api.InstancePlugin):
    order = colorbleed.api.ValidateContentsOrder + 0.05
    label = "Rig Controls No Inputs"
    hosts = ["maya"]
    families = ["colorbleed.rig"]
    actions = [colorbleed.api.RepairAction,
               colorbleed.maya.action.SelectInvalidAction]

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Controls have input connections: %s" % invalid)

    @classmethod
    def get_invalid(cls, instance):

        # Validate all controls
        invalid = []
        for control in get_controls(instance):
            if cls.get_connected_attributes(control):
                invalid.append(control)

        return invalid

    @staticmethod
    def get_connected_attributes(control):
        """Return attribute plugs with incoming connections.

        This will also get keyframes on unlocked keyable attributes.

        Args:
            control (str): Name of control node.

        Returns:
            list: The invalid plugs

        """

        attributes = cmds.listAttr(control, keyable=True, scalar=True)
        invalid = []
        for attr in attributes:

            # Ignore visibility attribute as that will
            # be forced to be locked anyway. As such we
            # don't care whether it has an incoming connection.
            if attr == "visibility":
                continue

            plug = "{}.{}".format(control, attr)

            # Ignore locked attributes
            locked = cmds.getAttr(plug, lock=True)
            if locked:
                continue

            # Check for incoming connections
            if cmds.listConnections(plug, source=True, destination=False):
                invalid.append(plug)

        return invalid

    @classmethod
    def repair(cls, instance):

        invalid = cls.get_invalid(instance)
        if not invalid:
            return

        # Use a single undo chunk
        with undo_chunk():
            for control in invalid:

                # Remove incoming connections
                invalid_plugs = cls.get_connected_attributes(control)
                for plug in invalid_plugs:
                    cls.log.info("Breaking input connection to %s" % plug)
                    source = cmds.listConnections(plug,
                                                  source=True,
                                                  destination=False,
                                                  plugs=True)[0]
                    cmds.disconnectAttr(source, plug)


class ValidateRigControlsDefaults(pyblish.api.InstancePlugin):
    """Validate rig controller default values.

    Controls must have the transformation attributes on their default
    values of translate zero, rotate zero and scale one when they are
    unlocked attributes.

    Unlocked keyable attributes may not have any incoming connections. If
    these connections are required for the rig then lock the attributes.

    Note that `repair` will:
        - Lock all visibility attributes
        - Reset all default values for translate, rotate, scale
        - Break all incoming connections to keyable attributes

    """
    order = colorbleed.api.ValidateContentsOrder + 0.05
    label = "Rig Controls Defaults"
    hosts = ["maya"]
    families = ["colorbleed.rig"]
    actions = [colorbleed.api.RepairAction,
               colorbleed.maya.action.SelectInvalidAction]

    # Default controller values
    CONTROLLER_DEFAULTS = {
        "translateX": 0,
        "translateY": 0,
        "translateZ": 0,
        "rotateX": 0,
        "rotateY": 0,
        "rotateZ": 0,
        "scaleX": 1,
        "scaleY": 1,
        "scaleZ": 1
    }

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Controls have non-default values: "
                               "%s" % invalid)

    @classmethod
    def get_invalid(cls, instance):

        invalid = list()
        for control in get_controls(instance):
            if cls.get_non_default_attributes(control):
                invalid.append(control)

        return invalid

    @classmethod
    def get_non_default_attributes(cls, control):
        """Return attribute plugs with non-default values

        Args:
            control (str): Name of control node.

        Returns:
            list: The invalid plugs

        """

        invalid = []
        for attr, default in cls.CONTROLLER_DEFAULTS.items():
            if cmds.attributeQuery(attr, node=control, exists=True):
                plug = "{}.{}".format(control, attr)

                # Ignore locked attributes
                locked = cmds.getAttr(plug, lock=True)
                if locked:
                    continue

                value = cmds.getAttr(plug)
                if value != default:
                    cls.log.warning("Control non-default value: "
                                    "%s = %s" % (plug, value))
                    invalid.append(plug)

        return invalid

    @classmethod
    def repair(cls, instance):

        invalid = cls.get_invalid(instance)
        if not invalid:
            return

        # Use a single undo chunk
        with undo_chunk():
            for control in invalid:

                # Reset non-default values
                invalid_plugs = cls.get_non_default_attributes(control)
                if invalid_plugs:
                    for plug in invalid_plugs:
                        attr = plug.split(".")[-1]
                        default = cls.CONTROLLER_DEFAULTS[attr]
                        cls.log.info("Setting %s to %s" % (plug, default))
                        cmds.setAttr(plug, default)
