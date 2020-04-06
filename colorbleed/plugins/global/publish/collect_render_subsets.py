import os
import re
import copy
import json
import pprint
from collections import defaultdict

import pyblish.api
from avalon import api
from colorbleed import schema


class CollectRenderSubsets(pyblish.api.InstancePlugin):
    """Collect the publishable subsets from the "filenames" data.

    Requires:
        instance    -> files

    Provides:
        instance    -> renderSubsets

    """

    order = pyblish.api.CollectorOrder + 0.45
    families = ["colorbleed.renderlayer",
                "colorbleed.usdrender",
                "redshift_rop"]
    label = "Collect Render Subsets"

    def process(self, instance):

        render_subsets = {}
        for path in instance.data["files"]:

            # Get subset from filename, ignoring any #### padding and the
            # extension
            # render.####.beauty.exr = render.beauty
            # render.beauty.####.exr = render.beauty
            fname = os.path.basename(path)
            fname_no_frames = re.sub("(.#+)", "", fname)
            subset, _ = os.path.splitext(fname_no_frames)

            if subset in render_subsets:
                existing = render_subsets[subset]
                self.log.warning("Found a render path resulting "
                                 "in a duplicate subset: %s (%s)" % (path,
                                                                     existing))
                continue

            render_subsets[subset] = path
        instance.data["renderSubsets"] = render_subsets
