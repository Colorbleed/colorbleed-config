import os

from avalon import api
from avalon.vendor import requests

import pyblish.api


def _get_script_dir():
    """Get path to the image sequence script"""
    try:
        import colorbleed
        scriptdir = os.path.dirname(colorbleed.__file__)
        fusion_scripts = os.path.join(scriptdir, "scripts", "fusion")
    except:
        raise RuntimeError("This is a bug")

    assert os.path.isdir(fusion_scripts), "Config is incomplete"
    fusion_scripts = fusion_scripts.replace(os.sep, "/")

    return fusion_scripts


class SubmitDependentSwitchJobDeadline(pyblish.api.ContextPlugin):
    """Run Switch Shot on specified comp as depending job

    """

    label = "Submit Switch Jobs to Deadline"
    order = pyblish.api.IntegratorOrder + 0.2
    hosts = ["maya"]
    families = ["colorbleed.renderlayer"]

    def process(self, context):

        # Run it as depend on the last submitted instance
        instance = context[-1]

        AVALON_DEADLINE = api.Session.get("AVALON_DEADLINE",
                                          "http://localhost:8082")
        assert AVALON_DEADLINE, "Requires AVALON_DEADLINE"

        job = instance.data.get("deadlineDependJob", None)
        if not job:
            self.log.warning("No dependent Job found")
            return True

        filepath = instance.data("flowFile", "")
        if not filepath:
            raise RuntimeError("No flow file (comp) chosen")

        shot = api.Session["AVALON_ASSET"]
        comment = instance.context.data["comment"]

        scriptdir = _get_script_dir()
        scriptfile = os.path.join(scriptdir, "deadline_switch_and_submit.py")

        args = '--file_path "{}" --asset_name "{}" --render 1'.format(
            filepath, shot)
        payload_name = "{} SWITCH".format(os.path.basename(filepath))

        payload = {
            "JobInfo": {
                "Plugin": "Python",
                "BatchName": job["Props"]["Batch"],
                "Name": payload_name,
                "JobType": "Normal",
                "JobDependency0": job["_id"],
                "UserName": job["Props"]["User"],
                "Comment": comment,
                "InitialStatus": "Active"},  # Set job pending
            "PluginInfo": {
                "Version": "3.6",
                "ScriptFile": scriptfile,
                "Arguments": args,
                "SingleFrameOnly": "True"
            },
            "AuxFiles": []
        }

        machine_limit = self.get_machine_limit(instance)
        payload["JobInfo"].update(machine_limit)

        environment = api.Session.copy()
        environment["AVALON_TOOLS"] = "global;python36"

        payload["JobInfo"].update({
            "EnvironmentKeyValue%d" % index: "{key}={value}".format(
                key=key,
                value=environment[key]
            ) for index, key in enumerate(environment)
        })

        url = "{}/api/jobs".format(AVALON_DEADLINE)
        response = requests.post(url, json=payload)
        if not response.ok:
            raise Exception(response.text)

        # Temporary key name, deadlineSubmissionJob was already taken
        if instance.data.get("runSlapComp", False):
            instance.data["deadlineDependJob"] = response.json()

        self.log.info("Slap comp arguments: %s" % args)

    def get_machine_limit(self, instance):
        """Retrieve the machine limit from the instance

        Args:
            instance: instance to retrieve the renderglobals from

        Returns:
            dict: {list type: list of machine names

        """

        renderglobals = instance.data.get("renderGlobals", None)
        if renderglobals is None:
            return {}

        if "Whitelist" in renderglobals:
            return {"Whitelist": renderglobals["Whitelist"]}

        return {"Blacklist": renderglobals.get("Blacklist")}
