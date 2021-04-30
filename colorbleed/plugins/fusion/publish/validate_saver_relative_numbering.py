import pyblish.api

from colorbleed import action


class ValidateSaverRelativeNumbering(pyblish.api.InstancePlugin):
    """Valid if all savers have the input attribute CreateDir checked on

    This attribute ensures that the folders to which the saver will write
    will be created.
    """

    order = pyblish.api.ValidatorOrder
    actions = [action.RepairAction]
    label = "Validate Saver-relative Numbering"
    families = ["colorbleed.saver"]
    hosts = ["fusion"]

    @classmethod
    def get_invalid(cls, instance):
        active = instance.data.get("active", instance.data.get("publish"))
        if not active:
            return []

        tool = instance[0]
        if tool.GetInput("SetSequenceStart"):
            cls.log.error("%s has Saver-relative Numbering on" %
                          instance[0].Name)
            return [tool]

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Found Saver with Saver-relative Numbering on")

    @classmethod
    def repair(cls, instance):
        invalid = cls.get_invalid(instance)
        for tool in invalid:
            tool.SetInput("SetSequenceStart", 0.0)
