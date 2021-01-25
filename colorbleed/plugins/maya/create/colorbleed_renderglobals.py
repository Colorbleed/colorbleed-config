from maya import cmds

import colorbleed.maya.lib as lib

from avalon.vendor import requests
import avalon.maya
from avalon import api


class CreateRenderGlobals(avalon.maya.Creator):
    """Submit Mayabatch renderlayers to Deadline"""

    label = "Render Globals"
    family = "colorbleed.renderglobals"
    icon = "gears"

    def __init__(self, *args, **kwargs):
        super(CreateRenderGlobals, self).__init__(*args, **kwargs)

        # We won't be publishing this one
        self.data["id"] = "avalon.renderglobals"

        # Get available Deadline pools
        AVALON_DEADLINE = api.Session["AVALON_DEADLINE"]
        argument = "{}/api/pools?NamesOnly=true".format(AVALON_DEADLINE)
        response = requests.get(argument)
        if not response.ok:
            self.log.warning("No pools retrieved")
            pools = []
        else:
            pools = response.json()

        # We don't need subset or asset attributes
        self.data.pop("subset", None)
        self.data.pop("asset", None)
        self.data.pop("active", None)

        self.data["suspendPublishJob"] = False
        self.data["extendFrames"] = False
        self.data["overrideExistingFrame"] = True
        self.data["useLegacyRenderLayers"] = not cmds.mayaHasRenderSetup()
        self.data["priority"] = 50
        self.data["framesPerTask"] = 1
        self.data["whitelist"] = False
        self.data["machineList"] = ""
        self.data["useMayaBatch"] = True
        self.data["primaryPool"] = pools
        # We add a string "-" to allow the user to not set any secondary pools
        self.data["secondaryPool"] = ["-"] + pools

        # Custom frame list so one can submit e.g. specific ranges
        # of frames in one go: 1-100, 300-500
        self.data["useCustomFrameList"] = False
        self.data["frameList"] = ""

        self.options = {"useSelection": False}  # Force no content

    def process(self):

        exists = cmds.ls(self.name)
        assert len(exists) <= 1, (
            "More than one renderglobal exists, this is a bug"
        )

        if exists:
            return cmds.warning("%s already exists." % exists[0])

        with lib.undo_chunk():
            super(CreateRenderGlobals, self).process()
            cmds.setAttr("{}.machineList".format(self.name), lock=True)
