import os
import copy
import logging
import shutil

import errno
import pyblish.api
from avalon import api, io, schema
import colorbleed.vendor.speedcopy as speedcopy

from colorbleed import lib

log = logging.getLogger(__name__)


class IntegrateAsset(pyblish.api.InstancePlugin):
    # Get docstring from library Integrator
    __doc__ = lib.Integrator.__doc__

    label = "Integrate Asset"
    order = pyblish.api.IntegratorOrder
    families = ["colorbleed.animation",
                "colorbleed.camera",
                "colorbleed.fbx",
                "colorbleed.imagesequence",
                "colorbleed.look",
                "colorbleed.mayaAscii",
                "colorbleed.model",
                "colorbleed.pointcache",
                "colorbleed.vdbcache",
                "colorbleed.setdress",
                "colorbleed.rig",
                "colorbleed.vrayproxy",
                "colorbleed.yetiRig",
                "colorbleed.yeticache",
                "colorbleed.review",
                "colorbleed.usd",
                "colorbleed.usd.bootstrap",
                "colorbleed.usd.layered",
                "usdModel",
                "usdShade",
                "usdSetDress",
                "usdPointcache"]
    targets = ["local"]

    def process(self, instance):

        self.log.info("Integrating into the database: {0}".format(instance))
        integrator = lib.Integrator()

        # Allow logging into the Plugin's logger.
        integrator.log = self.log

        integrator.process(instance)
