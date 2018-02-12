import os

import pyblish.api

from avalon import fusion


class CollectCurrentCompFusion(pyblish.api.ContextPlugin):
    """Collect current comp"""

    order = pyblish.api.CollectorOrder - 0.4
    label = "Collect Current Comp"
    hosts = ["fusion"]

    def process(self, context):
        """Collect all image sequence tools"""

        current_comp = fusion.get_current_comp()
        assert current_comp, "Must have active Fusion composition"
        context.data["currentComp"] = current_comp

        # Store path to current file
        attrs = current_comp.GetAttrs()
        filepath = attrs.get("COMPS_FileName", "")
        context.data['currentFile'] = filepath

        # Labelize the context
        context.data["label"] = os.path.basename(filepath)
