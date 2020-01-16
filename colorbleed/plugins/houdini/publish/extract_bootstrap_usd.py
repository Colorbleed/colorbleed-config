import os

import pyblish.api
import colorbleed.api
import colorbleed.houdini.usd as usdlib

from avalon import api, io


def _get_project_publish_template():
    """Return publish template from database for current project"""
    project = io.find_one({"type": "project"},
                          projection={"config.template.publish": True})
    return project["config"]["template"]["publish"]


class ExtractBootstrapUSD(colorbleed.api.Extractor):
    """Extract in-memory bootstrap USD files for Assets and Shots.

    See `collect_usd_bootstrap_asset.py` for more details.

    """

    order = pyblish.api.ExtractorOrder + 0.1
    label = "Bootstrap USD"
    hosts = ["houdini"]
    targets = ["local"]
    families = ["colorbleed.usd.bootstrap"]

    def process(self, instance):

        # This is crucial for the Integrator to integrate
        # it to the correct family in the end.
        family = "colorbleed.usd"
        instance.data["family"] = family
        instance.data["families"] = [family]

        staging_dir = self.staging_dir(instance)
        filename = "{subset}.usd".format(**instance.data)
        filepath = os.path.join(staging_dir, filename)
        self.log.info("Bootstrap USD '%s' to '%s'" % (filename, staging_dir))

        subset = instance.data["subset"]
        if subset == "usdAsset":
            # Asset
            steps = usdlib.PIPELINE["asset"]
            layers = self.get_usd_master_paths(steps, instance)
            usdlib.create_asset(filepath,
                                asset_name=instance.data["asset"],
                                reference_layers=layers)

        elif subset == "usdShot":
            # Shot
            steps = usdlib.PIPELINE["shot"]
            layers = self.get_usd_master_paths(steps, instance)
            usdlib.create_shot(filepath,
                               layers=layers)

        elif subset in usdlib.PIPELINE["asset"]:
            # Asset layer
            # Generate the stub files with root primitive
            usdlib.create_stub_usd(filepath)

        elif subset in usdlib.PIPELINE["shot"]:
            # Shot Layer
            # Generate the stub file for an Sdf Layer
            usdlib.create_stub_usd_sdf_layer(filepath)

        else:
            raise RuntimeError("No bootstrap method "
                               "available for: %s" % subset)

        if "files" not in instance.data:
            instance.data["files"] = []

        instance.data["files"].append(filename)

    def get_usd_master_paths(self, subsets, instance):

        asset = instance.data["asset"]

        template = _get_project_publish_template()
        layer_paths = []
        for layer in subsets:
            layer_path = self._get_usd_master_path(
                subset=layer,
                asset=asset,
                template=template
            )
            layer_paths.append(layer_path)
            self.log.info("Asset references: %s" % layer_path)

        return layer_paths

    def _get_usd_master_path(self,
                            subset,
                            asset,
                            template):
        """Get the filepath for a .usd file of a subset.

        This will return the path to an unversioned master file generated by
        `usd_master_file.py`.

        """

        PROJECT = api.Session["AVALON_PROJECT"]
        asset_doc = io.find_one({"name": asset,
                                 "type": "asset"})

        root = api.registered_root()
        path = template.format(**{
            "root": root,
            "project": PROJECT,
            "silo": asset_doc["silo"],
            "asset": asset_doc["name"],
            "subset": subset,
            "representation": "usd",    # force extension .usd
            "version": 0                # stub version zero
         })

        # Remove the version folder
        subset_folder = os.path.dirname(os.path.dirname(path))
        master_folder = os.path.join(subset_folder, "master")
        fname = "{0}.usd".format(subset)

        return os.path.join(master_folder, fname).replace("\\", "/")
