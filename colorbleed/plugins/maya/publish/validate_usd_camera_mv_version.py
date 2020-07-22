from distutils.version import LooseVersion

from maya import cmds

import pyblish.api


class ValidateUsdCameraMultiverseVersion(pyblish.api.Validator):
    """Validate Multiverse version is equal or higher than version 6.3.1"""

    order = pyblish.api.ValidatorOrder
    hosts = ["maya"]
    families = ["usdCamera"]
    label = "Multiverse version 6.3.1+"

    def process(self, instance):

        v = cmds.pluginInfo("MultiverseForMaya", query=True, version=True)
        assert v, "No version found for MultiverseForMaya"
        version = v.split("-", 1)[0]    # keep only "major.minor.patch"

        if LooseVersion(version) < LooseVersion("6.3.1"):
            raise ValueError("MultiverseForMaya must be version 6.3.1+. "
                             "You have version: %s -- Please install a newer "
                             "version of Multiverse." % v)
