from maya import cmds

import pyblish.api
import colorbleed.maya.action

from colorbleed.maya.lib import get_highest_in_hierarchy


class ValidateUSDModel(pyblish.api.Validator):
    """The USD Model must be exporting in a /geo root group.

    Make sure that the group you are exporting currently is named "geo".
    Any parents are ignored and not written, so you can publish multiple geo
    groups in the scene:

        /var1/geo/{geometry here}
        /var2/geo/..
        /var3/geo/..

    """

    order = pyblish.api.ValidatorOrder
    hosts = ["maya"]
    families = ["usdModel"]
    label = "USD Model"
    actions = [colorbleed.maya.action.SelectInvalidAction]

    @classmethod
    def get_invalid(cls, instance):
        roots = get_highest_in_hierarchy(instance)
        assert len(roots) == 1, "Must have a single root /geo"

        name = roots[0].rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if len(roots) != 1 or name != "geo":
            return roots

    def process(self, instance):
        """Process all the nodes in the instance "objectSet"""

        invalid = self.get_invalid(instance)
        if invalid:
            raise ValueError("Model root is not /geo, got: "
                             "{0}".format(invalid))
