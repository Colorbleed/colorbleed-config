import os
import json
import getpass

from maya import cmds

from avalon import api
from avalon.vendor import requests

import pyblish.api

import colorbleed.maya.lib as lib


def get_renderer_variables(renderlayer):
    """Retrieve the extension which has been set in the VRay settings

    Will return None if the current renderer is not VRay
    For Maya 2016.5 and up the renderSetup creates renderSetupLayer node which
    start with `rs`. Use the actual node name, do NOT use the `nice name`

    Args:
        renderlayer (str): the node name of the renderlayer.

    Returns:
        dict
    """

    renderer = lib.get_renderer(renderlayer)
    render_attrs = lib.RENDER_ATTRS.get(renderer, lib.RENDER_ATTRS["default"])

    # Get render settings (for the active renderer)
    padding = cmds.getAttr("{node}.{padding}".format(**render_attrs))
    filename_prefix = cmds.getAttr("{node}.{prefix}".format(**render_attrs))

    filename_0 = cmds.renderSettings(fullPath=True, firstImageName=True)[0]

    if renderer == "vray":
        # Maya's renderSettings function does not return V-Ray file extension
        # so we get the extension from vraySettings
        extension = cmds.getAttr("vraySettings.imageFormatStr")

        # When V-Ray image format has not been switched once from default .png
        # the getAttr command above returns None. As such we explicitly set
        # it to `.png`
        if extension is None:
            extension = "png"

    else:
        # Get the extension, getAttr defaultRenderGlobals.imageFormat
        # returns an index number.
        filename_base = os.path.basename(filename_0)
        extension = os.path.splitext(filename_base)[-1].strip(".")

    return {"ext": extension,
            "filename_prefix": filename_prefix,
            "padding": padding,
            "filename_0": filename_0}


class MayaSubmitRenderDeadline(pyblish.api.InstancePlugin):
    """Submit available render layers to Deadline

    Renders are submitted to a Deadline Web Service as
    supplied via the environment variable AVALON_DEADLINE.

    Target "local":
        Even though this does *not* render locally this is seen as
        a 'local' submission as it is the regular way of submitting
        a Maya render locally.

    """

    label = "Submit Render to Deadline"
    order = pyblish.api.IntegratorOrder
    hosts = ["maya"]
    families = ["colorbleed.renderlayer"]
    targets = ["local"]

    def process(self, instance):

        AVALON_DEADLINE = api.Session.get("AVALON_DEADLINE",
                                          "http://localhost:8082")
        assert AVALON_DEADLINE, "Requires AVALON_DEADLINE"

        context = instance.context
        workspace = context.data["workspaceDir"]
        code = context.data["code"]
        filepath = context.data["currentFile"]
        filename = os.path.basename(filepath)
        comment = context.data.get("comment", "")
        dirname = os.path.join(workspace, "renders")
        renderlayer = instance.data['setMembers']       # rs_beauty
        renderlayer_globals = instance.data["renderGlobals"]
        legacy_layers = renderlayer_globals["UseLegacyRenderLayers"]
        deadline_user = context.data.get("deadlineUser", getpass.getuser())
        jobname = "%s - %s" % (filename, instance.name)

        # If multiple cameras include the camera in the job's name
        camera = instance.data["camera"]
        if len(instance.data["cameras"]) > 1:
            # Get shortest unique path to camera transform
            transform = cmds.ls(cmds.listRelatives(camera,
                                                   parent=True,
                                                   fullPath=True))[0]
            jobname += " - " + transform

        # Support code prefix label for batch name
        batch_name = filename
        if code:
            batch_name = "{0} - {1}".format(code, batch_name)

        # Get the variables depending on the renderer
        render_variables = get_renderer_variables(renderlayer)

        try:
            # Ensure render folder exists
            os.makedirs(dirname)
        except OSError:
            pass

        # Documentation for keys available at:
        # https://docs.thinkboxsoftware.com
        #    /products/deadline/8.0/1_User%20Manual/manual
        #    /manual-submission.html#job-info-file-options
        payload = {
            "JobInfo": {
                # Top-level group name
                "BatchName": batch_name,

                # Job name, as seen in Monitor
                "Name": jobname,

                # Arbitrary username, for visualisation in Monitor
                "UserName": deadline_user,

                "Plugin": instance.data.get("mayaRenderPlugin", "MayaBatch"),
                "Frames": "{start}-{end}x{step}".format(
                    start=int(instance.data["startFrame"]),
                    end=int(instance.data["endFrame"]),
                    step=int(instance.data["byFrameStep"]),
                ),

                "Comment": comment
            },
            "PluginInfo": {
                # Input
                "SceneFile": filepath,

                # Output directory and filename
                "OutputFilePath": dirname.replace("\\", "/"),
                "OutputFilePrefix": render_variables["filename_prefix"],

                # Mandatory for Deadline
                "Version": cmds.about(version=True),

                # Only render layers are considered renderable in this pipeline
                "UsingRenderLayers": True,

                # Use legacy Render Layer system
                "UseLegacyRenderLayers": legacy_layers,

                # Render only this layer
                "RenderLayer": renderlayer,

                # Determine which renderer to use from the file itself
                "Renderer": instance.data["renderer"],

                # Resolve relative references
                "ProjectPath": workspace,

                # We are splitting renderlayer instances to a single renderable
                # camera on collection so just take the first one. However,
                # we still need to explicitly pass the render camera to
                # Deadline to ensure this task only renders that camera.
                "Camera": camera
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

        payload["JobInfo"].update({
            "EnvironmentKeyValue%d" % index: "{key}={value}".format(
                key=key,
                value=environment[key]
            ) for index, key in enumerate(environment)
        })

        # Include OutputFilename entries
        # The first entry also enables double-click to preview rendered
        # frames from Deadline Monitor
        payload["JobInfo"].update({
            "OutputFilename%d" % index: path.replace("\\", "/")
            for index, path in enumerate(instance.data["filenames"])
        })

        # Include optional render globals
        render_globals = instance.data.get("renderGlobals", {})
        payload["JobInfo"].update(render_globals)

        plugin = payload["JobInfo"]["Plugin"]
        self.log.info("using render plugin : {}".format(plugin))

        self.preflight_check(instance)

        self.log.info("Submitting..")
        self.log.info(json.dumps(payload, indent=4, sort_keys=True))

        # E.g. http://192.168.0.1:8082/api/jobs
        url = "{}/api/jobs".format(AVALON_DEADLINE)
        response = requests.post(url, json=payload)
        if not response.ok:
            raise Exception(response.text)

        # Store output dir for unified publisher (filesequence)
        output_dir = os.path.dirname(instance.data["filenames"][0])
        instance.data["outputDir"] = output_dir
        instance.data["deadlineSubmissionJob"] = response.json()

    def preflight_check(self, instance):
        """Ensure the startFrame, endFrame and byFrameStep are integers"""

        for key in ("startFrame", "endFrame", "byFrameStep"):
            value = instance.data[key]

            if int(value) == value:
                continue

            self.log.warning(
                "%f=%d was rounded off to nearest integer"
                % (value, int(value))
            )
