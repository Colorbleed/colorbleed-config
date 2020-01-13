import hou

import pyblish.api

from avalon import io
from avalon.houdini import lib
import colorbleed.houdini.usd as usdlib


class CollectUsdBootstrap(pyblish.api.InstancePlugin):
    """Collect special Asset/Shot bootstrap instances if those are needed.

    Some specific subsets are intended to be part of the default structure
    of an "Asset" or "Shot" in our USD pipeline. For example, for an Asset
    we layer a Model and Shade USD file over each other and expose that in
    a Asset USD file, ready to use.

    On the first publish of any of the components of a Asset or Shot the
    missing pieces are bootstrapped and generated in the pipeline too. This
    means that on the very first publish of your model the Asset USD file
    will exist too.

    """

    order = pyblish.api.CollectorOrder + 0.1
    label = "Collect USD Bootstrap"
    hosts = ["houdini"]
    families = ["colorbleed.usd"]

    # The predefined subset steps for a Shot and Asset
    shot_subsets_lookup = set(usdlib.SHOT_PIPELINE_SUBSETS)
    asset_subsets_lookup = set(usdlib.ASSET_PIPELINE_SUBSETS)

    def process(self, instance):

        instance_subset = instance.data["subset"]

        if instance_subset in self.shot_subsets_lookup:
            bootstrap = "shot"
        elif instance_subset in self.asset_subsets_lookup:
            bootstrap = "asset"
        else:
            self.log.debug("Ignoring bootstrap...")
            return

        asset = io.find_one({"name": instance.data["asset"],
                             "type": "asset"})
        assert asset, "Asset must exist: %s" % asset

        # Check which are not about to be created and don't exist yet
        required = {
            "shot": usdlib.SHOT_PIPELINE_SUBSETS + ["usdShot"],
            "asset": usdlib.ASSET_PIPELINE_SUBSETS + ["usdAsset"]
        }.get(bootstrap)

        self.log.debug("Checking required bootstrap: %s" % list(required))

        for subset in required:
            if self._subset_exists(instance, subset, asset):
                continue

            self.log.debug("Creating {0} USD bootstrap: {1} {2}".format(
                bootstrap,
                asset["name"],
                subset
            ))

            new = instance.context.create_instance(subset)
            new.data["subset"] = subset
            new.data["label"] = "{0} ({1})".format(subset, asset["name"])
            new.data["family"] = "colorbleed.usd.bootstrap"
            new.data["comment"] = "Automated bootstrap USD file."

            # Copy some data from the instance for which we bootstrap
            for key in ["asset", "id"]:
                new.data[key] = instance.data[key]

    def _subset_exists(self, instance, subset, asset):
        """Return whether subset exists in current context or in database."""

        # Allow it to be created during this publish session
        context = instance.context
        for inst in context:
            if inst.data["subset"] == subset:
                return True

        # Or, if they already exist in the database we can
        # skip them too.
        if io.find_one({"name": subset,
                        "type": "subset",
                        "parent": asset["_id"]}):
            return True

        return False
