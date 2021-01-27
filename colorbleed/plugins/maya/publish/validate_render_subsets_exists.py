import pyblish.api

import colorbleed.maya.action
from avalon import io
import colorbleed.api


def subset_exists(asset_name, subset_name):
    """Check if subset is registered in the database under the asset"""

    asset = io.find_one({"type": "asset", "name": asset_name})
    subset = io.find_one({"type": "subset",
                          "name": subset_name,
                          "parent": asset["_id"]})
    return bool(subset)


class ValidateRenderSubsetsExists(pyblish.api.InstancePlugin):
    """Validate rendered subsets are already registered in the database.

    This validation is only required whenever Extend Frames is enabled for
    the render publish, because it will require pre-existing publishes of
    subsets to exist.

    Each render element is registered as a subset which is formatted based on
    the render layer and the render element, example:

        <render layer>.<render element>

    This translates to something like this:

        CHAR.diffuse

    """

    order = pyblish.api.ValidatorOrder + 0.1
    label = "Render Subsets Exist"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer"]
    actions = [colorbleed.maya.action.SelectInvalidAction]

    def process(self, instance):

        if not instance.data("extendFrames", False):
            # This check is only relevant when extendFrames is enabled.
            return

        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Found unregistered subsets: "
                               "{}".format(invalid))

    @classmethod
    def get_invalid(cls, instance):

        invalid = []

        asset_name = instance.data["asset"]
        subsets = instance.data["renderSubsets"].keys()

        for subset in subsets:
            if not subset_exists(asset_name, subset):
                invalid.append(subset)

        return invalid


