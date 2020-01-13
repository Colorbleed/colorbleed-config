from avalon import api
from avalon.houdini import lib
import hou


class _USDWorkspace(api.Creator):
    """Base class to create pre-built USD Workspaces"""

    node_name = None
    node_type = None
    step = None
    icon = "gears"

    def process(self):

        if not all([self.node_type, self.node_name, self.step]):
            self.log.error("Incomplete USD Workspace parameters")
            return

        name = self.node_name
        node_type = self.node_type

        # Force the subset to "{asset}.{step}.usd"
        subset = "usd{step}".format(step=self.step)
        self.data["subset"] = subset

        # Get stage root and create node
        stage = hou.node("/stage")
        instance = stage.createNode(node_type, node_name=name)
        instance.moveToGoodPosition()

        # With the Workspace HDAs there is no need to imprint the instance data
        # since this data is pre-built into it. However, we do set the right
        # asset as that can be defined by the user.
        parms = {
            "asset": self.data["asset"],
            # This is just so it has a good default value
            # TODO build this into the HDA
            "lopoutput": "$HIP/usd/%s.usd" % subset
         }
        instance.setParms(parms)

        return instance


class USDCreateModelingWorkspace(_USDWorkspace):
    """USD Modeling Workspace"""

    defaults = ["Model"]

    label = "USD Modeling Workspace"
    family = "colorbleed.model.usd"

    node_type = "cb::modeling_workspace::1.1"
    node_name = "modelingWorkspace"
    step = "Model"


class USDCreateShadingWorkspace(_USDWorkspace):
    """USD Shading Workspace"""

    defaults = ["Shade"]

    label = "USD Shading Workspace"
    family = "colorbleed.shade.usd"

    node_type = "cb::shadingWorkspace::1.0"
    node_name = "shadingWorkspace"
    step = "Shade"

    def process(self):

        raise NotImplementedError("Shading workspace HDA needs to be updated.")

        instance = super(USDCreateShadingWorkspace, self).process()

        # Set published file path for this one?
        instance.setParms({
            "filepath1": "$HIP/usd/usdModel.usd"
        })

# Don't allow the base class to be picked up by Avalon
del _USDWorkspace