import re

import pyblish.api

from avalon import io
import colorbleed.usdlib as usdlib


class CollectUsdModelBootstrap(pyblish.api.InstancePlugin):
    """Collect special Asset bootstrap instances if those are needed.

    On creating a usdModel we bootstrap the usdAsset and its usdModel/usdShade.

        - usdAsset must just exist
        - usdModel/usdShade must be updated if there are new model variations

    """

    order = pyblish.api.CollectorOrder + 0.35
    label = "Collect USD Model bootstrap"
    hosts = ["houdini", "maya"]
    families = ["usdModel"]

    def process(self, instance):

        asset = io.find_one({"name": instance.data["asset"],
                             "type": "asset"})
        assert asset, "Asset must exist: %s" % asset

        # Create the usdAsset only the first time
        if not self.subset_exists(instance, "usdAsset", asset):
            self.create_instance(instance,
                                 subset="usdAsset",
                                 asset=asset)

        # Create the usdModel and usdShade whenever it requires a new
        # combination of model variations.
        if not self.subset_exists(instance, "usdModel", asset,
                                  check_database=False):
            # When the usdModel is not in the instance list yet add it
            # Get existing model variations
            variant_subsets = self.get_variants(instance, asset)

            self.log.info("Subsets: %s" % variant_subsets)

            for subset in ["usdModel", "usdShade"]:
                self.create_instance(instance,
                                     subset=subset,
                                     asset=asset,
                                     data={"variantSubsets": variant_subsets})

    def get_variants(self, instance, asset):

        # Subsets in database
        variant_subsets = set()
        name = re.compile(r"usdModel.+")
        for subset in io.find({"name": name,
                               "type": "subset",
                               "parent": asset["_id"]}):

            # Ignore subsets that have been tagged deprecated to
            # allow "removing" wrong models from the asset for
            # future publishes
            tags = subset["data"].get("tags")
            if tags and "deprecated" in tags:
                continue

            variant_subsets.add(subset["name"])

        # To be generated new instances in this publish
        for i in instance.context:

            if not i.data.get("active", True):
                continue

            if not i.data.get("publish", True):
                continue

            if i.data["asset"] != asset["name"]:
                continue

            subset = i.data["subset"]
            if name.match(subset):
                variant_subsets.add(subset)

        variant_subsets = list(sorted(variant_subsets))

        # Force usdModelDefault to be the first and default variant.
        default = None
        for subset in variant_subsets:
            if subset == "usdModelDefault":
                default = subset
                break

        if default and default != variant_subsets[0]:
            variant_subsets.remove(default)
            variant_subsets.insert(0, default)

        return variant_subsets

    def create_instance(self, instance, subset, asset,
                        data=None):

        self.log.debug("Creating: {0} {1}".format(
            asset["name"],
            subset
        ))

        new = instance.context.create_instance(subset)
        new.data["subset"] = subset
        new.data["label"] = "{0} ({1})".format(subset, asset["name"])
        new.data["family"] = "colorbleed.usd.bootstrap"
        new.data["publishFamilies"] = ["colorbleed.usd"]

        # Do not allow the user to toggle this instance
        new.data["optional"] = False

        # Copy some data from the instance for which we bootstrap
        for key in ["asset"]:
            new.data[key] = instance.data[key]

        # Optional keys
        for key in ["inputs", "comment"]:
            if key in instance.data:
                new.data[key] = instance.data[key]

        if data:
            new.data.update(data)

    def subset_exists(self,
                      instance,
                      subset,
                      asset,
                      check_instances=True,
                      check_database=True):
        """Return whether subset exists in current context or in database."""

        # Allow it to be created during this publish session
        if check_instances:
            context = instance.context
            for inst in context:
                if inst.data["subset"] == subset:
                    if inst.data["asset"] != asset["name"]:
                        # Ignore instances that are for another asset
                        continue

                    return True

        if check_database:
            # Or, if they already exist in the database we can
            # skip them too.
            if io.find_one({"name": subset,
                            "type": "subset",
                            "parent": asset["_id"]}):
                return True

        return False
