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

        parms = {
             "lopoutput": "$HIP/usd/%s.usd" % subset
         }
        instance.setParms(parms)

        # Avoid the "active" state?
        self.data.pop("active", None)

        # Imprint avalon data
        lib.imprint(instance, self.data)

        # Lock any parameters in this list
        to_lock = ["id", "family", "subset"]
        for name in to_lock:
            parm = instance.parm(name)
            parm.lock(True)

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
        instance = super(USDCreateShadingWorkspace, self).process()

        # Set published file path for this one?
        instance.setParms({
            "filepath1": "$HIP/usd/usdModel.usd"
        })

# Don't allow the base class to be picked up by Avalon
del _USDWorkspace
