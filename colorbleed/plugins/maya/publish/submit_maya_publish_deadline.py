import os
import json
import getpass

from maya import cmds

from avalon import api, io
from avalon.vendor import requests

import pyblish.api

import colorbleed.maya.lib as lib


def _get_script():
    """Get path to the deadline script to run"""

    import pkgutil

    module = "colorbleed.scripts.publish_instances"
    loader = pkgutil.get_loader(module)
    if not loader:
        raise RuntimeError("Couldn't resolve module '%s'" % module)

    module_path = loader.filename
    if module_path.endswith(".pyc"):
        module_path = module_path[:-len(".pyc")] + ".py"

    return module_path


class MayaSubmitPublishDeadline(pyblish.api.ContextPlugin):
    """Submit Maya scene to perform a local publish in Deadline.

    Publishing in Deadline can be helpful for scenes that publish very slow.
    This way it can process in the background on another machine without the
    Artist having to wait for the publish to finish on their local machine.

    Submission is done through the Deadline Web Service as
    supplied via the environment variable AVALON_DEADLINE.

    """

    label = "Submit Scene to Deadline"
    order = pyblish.api.IntegratorOrder
    hosts = ["maya"]
    families = ["*"]
    targets = ["deadline"]

    def process(self, context):

        # Ensure no errors so far
        assert all(result["success"] for result in context.data["results"]), (
            "Errors found, aborting integration..")

        # Deadline connection
        AVALON_DEADLINE = api.Session.get("AVALON_DEADLINE",
                                          "http://localhost:8082")
        assert AVALON_DEADLINE, "Requires AVALON_DEADLINE"

        # Note that `publish` data member might change in the future.
        # See: https://github.com/pyblish/pyblish-base/issues/307
        actives = [i for i in context if i.data["publish"]]
        instance_names = sorted(instance.name for instance in actives)

        if not instance_names:
            self.log.warning("No active instances found. "
                             "Skipping submission..")
            return

        scene = context.data["currentFile"]
        scenename = os.path.basename(scene)

        # Get project code
        project = io.find_one({"type": "project"})
        code = project["data"].get("code", project["name"])

        job_name = "{scene} [PUBLISH]".format(scene=scenename)
        batch_name = "{code} - {scene}".format(code=code, scene=scenename)
        deadline_user = "roy"  # todo: get deadline user dynamically

        # Generate the payload for Deadline submission
        payload = {
            "JobInfo": {
                "Plugin": "MayaBatch",
                "BatchName": batch_name,
                "Priority": 50,
                "Name": job_name,
                "UserName": deadline_user,
                # "Comment": instance.context.data.get("comment", ""),
                # "InitialStatus": state

            },
            "PluginInfo": {

                "Build": None,  # Don't force build
                "StrictErrorChecking": True,
                "ScriptJob": True,

                # Inputs
                "SceneFile": scene,
                "ScriptFilename": _get_script(),

                # Mandatory for Deadline
                "Version": cmds.about(version=True),

                # Resolve relative references
                "ProjectPath": cmds.workspace(query=True,
                                              rootDirectory=True),

            },

            # Mandatory for Deadline, may be empty
            "AuxFiles": []
        }

        # Include critical environment variables with submission + api.Session
        keys = [
            # Submit along the current Avalon tool setup that we launched
            # this application with so the Render Slave can build its own
            # similar environment using it, e.g. "maya2018;vray4.x;yeti3.1.9"
            "AVALON_TOOLS",
        ]
        environment = dict({key: os.environ[key] for key in keys
                            if key in os.environ}, **api.Session)
        environment["PYBLISH_ACTIVE_INSTANCES"] = ",".join(instance_names)

        payload["JobInfo"].update({
            "EnvironmentKeyValue%d" % index: "{key}={value}".format(
                key=key,
                value=environment[key]
            ) for index, key in enumerate(environment)
        })

        self.log.info("Submitting..")
        self.log.info(json.dumps(payload, indent=4, sort_keys=True))

        # E.g. http://192.168.0.1:8082/api/jobs
        url = "{}/api/jobs".format(AVALON_DEADLINE)
        response = requests.post(url, json=payload)
        if not response.ok:
            raise Exception(response.text)
