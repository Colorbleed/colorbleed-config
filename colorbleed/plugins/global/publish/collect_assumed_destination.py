import os
import pyblish.api

from avalon import io, api


class CollectAssumedDestination(pyblish.api.InstancePlugin):
    """Generate the assumed destination path where the file will be stored"""

    label = "Collect Assumed Destination"
    order = pyblish.api.CollectorOrder + 0.499

    def process(self, instance):
        """Create a destination filepath based on the current data available

        Example template:
            {root}/{project}/{silo}/{asset}/publish/{subset}/v{version:0>3}/
            {subset}.{representation}

        """

        # get all the stuff from the database
        subset_name = instance.data["subset"]
        asset_name = instance.data["asset"]
        project_name = api.Session["AVALON_PROJECT"]

        project = io.find_one({"type": "project",
                               "name": project_name},
                              projection={"config": True})

        template = project["config"]["template"]["publish"]

        asset = io.find_one({"type": "asset",
                             "name": asset_name,
                             "parent": project["_id"]})

        assert asset, ("No asset found by the name '{}' "
                       "in project '{}'".format(asset_name, project_name))
        silo = asset['silo']

        subset = io.find_one({"type": "subset",
                              "name": subset_name,
                              "parent": asset["_id"]})

        # assume there is no version yet, we start at `1`
        version = None
        version_number = 1
        if subset is not None:
            version = io.find_one({"type": "version",
                                   "parent": subset["_id"]},
                                  sort=[("name", -1)])

        # if there is a subset there ought to be version
        if version is not None:
            version_number += version["name"]

        template_data = {"root": api.Session["AVALON_PROJECTS"],
                         "project": project_name,
                         "silo": silo,
                         "asset": asset_name,
                         "subset": subset_name,
                         "version": version_number,
                         "representation": "TEMP"}

        instance.data["template"] = template
        instance.data["assumedTemplateData"] = template_data

        # We take the parent folder of representation 'filepath'
        instance.data["assumedDestination"] = os.path.dirname(
            template.format(**template_data)
        )
