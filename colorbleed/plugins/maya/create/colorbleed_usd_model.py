import avalon.maya


class CreateUSDModel(avalon.maya.Creator):
    """USD Polygonal static geometry"""

    label = "USD Model"
    family = "usdModel"
    icon = "cube"

    def __init__(self, *args, **kwargs):
        super(CreateUSDModel, self).__init__(*args, **kwargs)

        # Whether to include parent hierarchy of nodes in the instance
        self.data["includeParentHierarchy"] = False
