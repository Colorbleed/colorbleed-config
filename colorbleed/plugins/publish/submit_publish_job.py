import os
import json
import re

from avalon import api
from avalon.vendor import requests

import pyblish.api


def _get_script():
    """Get path to the image sequence script"""
    try:
        from colorbleed.scripts import publish_filesequence
    except Exception as e:
        raise RuntimeError("Expected module 'publish_imagesequence'"
                           "to be available")

    module_path = publish_filesequence.__file__
    if module_path.endswith(".pyc"):
        module_path = module_path[:-len(".pyc")] + ".py"

    return module_path


class SubmitDependentImageSequenceJobDeadline(pyblish.api.InstancePlugin):
    """Submit image sequence publish jobs to Deadline.

    These jobs are dependent on a deadline job submission prior to this
    plug-in.

    Renders are submitted to a Deadline Web Service as
    supplied via the environment variable AVALON_DEADLINE

    Options in instance.data:
        - deadlineSubmission (dict, Required): The returned .json
            data from the job submission to deadline.

        - outputDir (str, Required): The output directory where the metadata
            file should be generated. It's assumed that this will also be
            final folder containing the output files.

        - ext (str, Optional): The extension (including `.`) that is required
            in the output filename to be picked up for image sequence
            publishing.

        - publishJobState (str, Optional): "Active" or "Suspended"
            This defaults to "Suspended"

    This requires a "startFrame" and "endFrame" to be present in instance.data
    or in context.data.

    """

    label = "Submit image sequence jobs to Deadline"
    order = pyblish.api.IntegratorOrder + 0.1
    hosts = ["fusion", "maya"]
    families = ["colorbleed.saver.deadline", "colorbleed.renderlayer"]

    def process(self, instance):

        AVALON_DEADLINE = api.Session.get("AVALON_DEADLINE",
                                          "http://localhost:8082")
        assert AVALON_DEADLINE, "Requires AVALON_DEADLINE"

        # Get a submission job
        job = instance.data.get("deadlineSubmissionJob")
        if not job:
            raise RuntimeError("Can't continue without valid deadline "
                               "submission prior to this plug-in.")

        subset = instance.data["subset"]
        state = instance.data.get("publishJobState", "Suspended")
        job_name = "{batch} - {subset} [publish image sequence]".format(
            batch=job["Props"]["Name"],
            subset=subset
        )

        # Add in start/end frame
        context = instance.context
        start = instance.data.get("startFrame", context.data["startFrame"])
        end = instance.data.get("endFrame", context.data["endFrame"])

        # Add in regex for sequence filename
        # This assumes the output files start with subset name and ends with
        # a file extension.
        if "ext" in instance.data:
            ext = re.escape(instance.data["ext"])
        else:
            ext = "\.\D+"

        regex = "^{subset}.*\d+{ext}$".format(subset=re.escape(subset),
                                              ext=ext)

        # Write metadata for publish job
        data = instance.data.copy()
        data.pop("deadlineSubmissionJob")
        metadata = {
            "regex": regex,
            "startFrame": start,
            "endFrame": end,
            "families": ["colorbleed.imagesequence"],

            # Optional metadata (for debugging)
            "metadata": {
                "instance": data,
                "job": job,
                "session": api.Session.copy()
            }
        }

        # Ensure output dir exists
        output_dir = instance.data["outputDir"]
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir)

        metadata_filename = "{}_metadata.json".format(subset)
        metadata_path = os.path.join(output_dir, metadata_filename)
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=4, sort_keys=True)

        # Generate the payload for Deadline submission
        payload = {
            "JobInfo": {
                "Plugin": "Python",
                "BatchName": job["Props"]["Batch"],
                "Name": job_name,
                "JobType": "Normal",
                "JobDependency0": job["_id"],
                "UserName": job["Props"]["User"],
                "Comment": instance.context.data.get("comment", ""),
                "InitialStatus": state
            },
            "PluginInfo": {
                "Version": "3.6",
                "ScriptFile": _get_script(),
                "Arguments": '--path "{}"'.format(metadata_path),
                "SingleFrameOnly": "True"
            },

            # Mandatory for Deadline, may be empty
            "AuxFiles": []
        }

        # Transfer the environment from the original job to this dependent
        # job so they use the same environment
        environment = job["Props"].get("Env", {})
        payload["JobInfo"].update({
            "EnvironmentKeyValue%d" % index: "{key}={value}".format(
                key=key,
                value=environment[key]
            ) for index, key in enumerate(environment)
        })

        self.log.info("Submitting..")
        self.log.info(json.dumps(payload, indent=4, sort_keys=True))

        url = "{}/api/jobs".format(AVALON_DEADLINE)
        response = requests.post(url, json=payload)
        if not response.ok:
            raise Exception(response.text)

        # Temporary key name, deadlineSubmissionJob was already taken
        if instance.data("runSlapComp", False):
            instance.data["deadlineDependJob"] = response.json()
