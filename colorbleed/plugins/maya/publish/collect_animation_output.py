import os

import pyblish.api


class CollectAnimationOutputFamily(pyblish.api.InstancePlugin):
    """Decide whether to Extract USD or Alembic for animation"""

    order = pyblish.api.CollectorOrder + 0.1
    families = ["colorbleed.animation"]
    label = "Animation Output Family"
    hosts = ["maya"]

    def process(self, instance):
        """Collect the hierarchy nodes"""

        is_usd_project = (os.environ.get("CB_ANIMATION_AS_USD", None)
                          not in {"0", None})

        families = instance.data.get("families", [])

        if is_usd_project:
            families.append("colorbleed.animation.usd")
        else:
            families.append("colorbleed.animation.abc")

        instance.data["families"] = families
