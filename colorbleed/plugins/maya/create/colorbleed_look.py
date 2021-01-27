import avalon.maya
from colorbleed.maya import lib
from maya import cmds


class CreateLook(avalon.maya.Creator):
    """Shader connections defining shape look"""

    label = "Look"
    family = "colorbleed.look"
    icon = "paint-brush"

    def __init__(self, *args, **kwargs):
        super(CreateLook, self).__init__(*args, **kwargs)

        renderlayer = cmds.editRenderLayerGlobals(query=True,
                                                  currentRenderLayer=True)
        self.data["renderlayer"] = renderlayer
