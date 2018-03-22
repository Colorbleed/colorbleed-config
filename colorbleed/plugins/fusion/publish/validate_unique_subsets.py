import pyblish.api


class ValidateUniqueSubsets(pyblish.api.InstancePlugin):
    """Ensure all instances have a unique subset name"""

    order = pyblish.api.ValidatorOrder
    label = "Validate Unique Subsets"
    families = ["colorbleed.saver"]
    hosts = ["fusion"]

    @classmethod
    def get_invalid(cls, instance):
        context = instance.context
        subset = instance.data["subset"]
        for other_instance in list(context):
            if other_instance == instance:
                continue

            if other_instance.data["subset"] == subset:
                return [instance]   # current instance is invalid

        return []

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Content is invalid. See log.")
