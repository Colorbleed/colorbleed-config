import os
import avalon.api as api
import avalon.io as io

import pyblish.api


def is_in_folder(root, folder):
    return os.path.realpath(folder).startswith(os.path.realpath(root))


class ValidateFusionCompMatchesAsset(pyblish.api.ContextPlugin):
    """Ensure current comp is saved within the asset.
    
    This is to avoid "wrong" publishes towards an invalid asset
    since that is somewhat trivial to happen in Fusion due to
    the Context not being set per open Comp but for Fusion as a whole.
    And since multiple comps can be open at the same time, this can
    result in confusing results.
    
    """

    order = pyblish.api.ValidatorOrder
    label = "Validate Comp Matches Asset"
    families = ["colorbleed.saver"]
    hosts = ["fusion"]

    def process(self, context):
    
        asset_name = instance.data["asset"]
        project_name = api.Session["AVALON_PROJECT"]
    
        comp = context.data.get("currentComp")
        assert comp, "Must have Comp object"
        attrs = comp.GetAttrs()

        filename = attrs["COMPS_FileName"]
        if not filename:
            raise RuntimeError("Comp is not saved.")

        # The work file template for this project
        project = io.find_one({"type": "project",
                               "name": project_name},
                              projection={"config": True})
        template = project["config"]["template"]["work"]

        # Get the path up to the first formattable variable
        # after the "{asset}" to use as asset root.
        pre, sep, post = template.partition("{asset}")
        asset_template = pre + sep + post.split("{", 1)[0]

        # Get silo for the asset
        asset = io.find_one({"type": "asset",
                             "name": asset_name,
                             "parent": project["_id"]})
        assert asset, ("No asset found by the name '{}' "
                       "in project '{}'".format(asset_name, project_name))
        silo = asset.get("silo", None)
        if "{silo}" in asset_template and not silo:
            self.log.error("No silo set silo data is required "
                           "in template: %s" % asset_template)
            raise RuntimeError("Missing silo data for work asset root template.")

        template_data = {"root": api.Session["AVALON_PROJECTS"],
                         "project": project_name,
                         "silo": silo,
                         "asset": asset_name,
                         "task": api.Session["AVALON_TASK"]}

        asset_root = asset_template.format(**template_data)
        if not is_in_folder(filename, root=asset_root):
            # Not inside the asset root
            raise RuntimeError("Comp isn't saved inside asset '%s': %s" % (asset_name, filename))

