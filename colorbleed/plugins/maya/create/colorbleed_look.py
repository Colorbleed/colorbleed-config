import avalon.maya
from colorbleed.maya import lib


class CreateLook(avalon.maya.Creator):
    """Shader connections defining shape look"""

    name = "look"
    label = "Look"
    family = "colorbleed.look"
    icon = "paint-brush"

    def __init__(self, *args, **kwargs):
        super(CreateLook, self).__init__(*args, **kwargs)

        self.data["renderlayer"] = lib.get_current_renderlayer()

        # Whether to automatically convert the textures to .tx upon publish.
        self.data["maketx"] = True
