import os
import json
import pprint
import re
from collections import defaultdict

from avalon import api, io
from avalon.vendor import requests, clique

from colorbleed.vendor import speedcopy
from colorbleed import schema

import pyblish.api


def _get_script():
    """Get path to the Publish Job script"""
    try:
        from colorbleed.scripts import publish_job
    except Exception as exc:
        print("Exception occurred: %s" % exc)
        raise RuntimeError("The 'publish_job' script"
                           " is not available..")

    module_path = publish_job.__file__
    if module_path.endswith(".pyc"):
        module_path = module_path[:-len(".pyc")] + ".py"

    return module_path


# Logic to retrieve latest files concerning extendFrames
def get_latest_version(asset_name, subset_name, family):
    # Get asset
    asset = io.find_one({"type": "asset",
                         "name": asset_name},
                        projection={"name": True})
    subset = io.find_one({"type": "subset",
                          "name": subset_name,
                          "parent": asset["_id"]},
                         projection={"_id": True,
                                     "name": True,
                                     "schema": True,
                                     "data.families": True})

    # Check if subsets actually exists
    assert subset, "Subset %s (%s) does not exist, " \
                   "please publish with `extendFrames` off" % (subset_name,
                                                               asset_name)

    schema = subset.get("schema")
    is_new_style_subset = schema == 'avalon-core:subset-3.0'
    if is_new_style_subset:
        # New style subsets have data.families on the subset
        if family not in subset["data"]["families"]:
            raise RuntimeError(
                "Subset %s is not of family: %s" % (subset_name, family))

    # Get version
    version_projection = {"name": True,
                          "data.startFrame": True,
                          "data.endFrame": True,
                          "data.families": True,
                          "parent": True}

    version = io.find_one({"type": "version",
                           "parent": subset["_id"]},
                          projection=version_projection,
                          sort=[("name", -1)])

    if not is_new_style_subset:
        # Old style subsets have data.families on the versions
        if family not in version["data"]["families"]:
            raise RuntimeError(
                "Subset->Version %s->%s is not of family: %s" % (
                    subset_name, "v{0:03d}".format(version["name"]), family
                ))

    assert version, "No version found for %s > %s (%s), this is a bug" % (
        asset_name, subset_name, family
    )

    return version


def get_resources(version, extension=None):
    """
    Get the files from the specific version
    """
    query = {"type": "representation", "parent": version["_id"]}
    if extension:
        query["name"] = extension

    representation = io.find_one(query)
    assert representation, "This is a bug"

    directory = api.get_representation_path(representation)
    resources = sorted([os.path.normpath(os.path.join(directory, fname))
                        for fname in os.listdir(directory)])

    return resources


def get_resource_files(resources, frame_range, override=True):
    res_collections, _ = clique.assemble(resources)
    assert len(res_collections) == 1, "Multiple collections found"
    res_collection = res_collections[0]

    # Remove any frames
    if override:
        for frame in frame_range:
            if frame not in res_collection.indexes:
                continue
            res_collection.indexes.remove(frame)

    return list(res_collection)


def compute_publish_from_instance(instance):
    """Compute publish instance data from "renderSubsets" data.

    This also uses the other data of the instance and context to produce
    a full publish instance, like e.g. copying over the startFrame and endFrame
    data for the instance or 'user', 'currentFile', 'fps', 'comment' on the
    context.

    """

    assert instance.data["renderSubsets"]

    publish_context = {}
    publish_instances = []

    # Create publish context
    context = instance.context
    optional_context_keys = ["user", "currentFile", "fps", "comment"]
    for key in optional_context_keys:
        if key in context.data:
            publish_context[key] = context.data[key]

    # Create publish instances
    for subset, path in instance.data["renderSubsets"].items():

        if "frames" in instance.data:
            # Explicit frames
            frames = instance.data["frames"]
        else:
            # Start/end frame range
            start = int(instance.data["startFrame"])
            end = int(instance.data["endFrame"])
            frames = range(start, end+1)

        def replace_frame_padding(match):
            """Replace #### padding with {0:04d}"""
            padding = len(match.group(0))
            return "{{0:0{0}d}}".format(padding)

        fname = os.path.basename(path)
        frame_str = re.sub(r"(#+)", replace_frame_padding, fname)
        files = [frame_str.format(i) for i in frames]

        publish_instance = {
            "subset": subset,
            "families": ["colorbleed.imagesequence"],
            # Add the sequence of files into a list to ensure full sequence is
            # seen as a single representation when the publish integrates it
            "files": [files],
            "stagingDir": os.path.dirname(path).replace("\\", "/")
        }

        # Transfer key/values from instance
        required = ["asset"]
        for key in required:
            publish_instance[key] = instance.data[key]

        optional = ["startFrame",
                    "endFrame",
                    "frames",       # explicit frames
                    "handles",
                    "inputs"]
        for key in optional:
            if key in instance.data:
                publish_instance[key] = instance.data[key]

        publish_instances.append(publish_instance)

    payload = {
        "schema": "standalonepublish-1.0",
        "context": publish_context,
        "instances": publish_instances
    }

    schema.validate(payload)

    return payload


class SubmitDependentImageSequenceJobDeadline(pyblish.api.InstancePlugin):
    """Submit image sequence publish jobs to Deadline.

    These jobs are dependent on a deadline job submission prior to this
    plug-in.

    Renders are submitted to a Deadline Web Service as
    supplied via the environment variable AVALON_DEADLINE

    Requires:
        instance ->     deadlineSubmission (dict)
            The returned .json data from the job submission to deadline.
        instance ->     outputDir (str)
            The output directory where the metadata file should be generated.
            It's assumed that this will also be final folder containing the
            output files.
        instance ->     startFrame (float or int)
        instance ->     endFrame (float or int)

    Optional:
        instance ->     publishJobState (str)
            "Active" or "Suspended". This defaults to "Active"
        instance ->     frames (tuple of int)
            Explicit frames list. Overrides startFrame/endFrame.

    """

    label = "Submit Publish Job to Deadline"
    order = pyblish.api.IntegratorOrder + 0.1
    hosts = ["fusion", "maya", "houdini"]
    families = ["colorbleed.saver.deadline",
                "colorbleed.renderlayer",
                "colorbleed.vrayscene",
                "colorbleed.usdrender",
                "redshift_rop"]
    targets = ["local"]

    def process(self, instance):

        AVALON_DEADLINE = api.Session.get("AVALON_DEADLINE",
                                          "http://localhost:8082")
        assert AVALON_DEADLINE, "Requires AVALON_DEADLINE"

        # Get a submission job
        job = instance.data.get("deadlineSubmissionJob")
        if not job:
            raise RuntimeError("Can't continue without valid deadline "
                               "submission prior to this plug-in.")

        data = instance.data.copy()
        subset = data["subset"]
        state = data.get("publishJobState", "Active")

        # Construct job name based on Render Job name and data.
        job_name = "{name} [publish image sequence]".format(
            name=job["Props"]["Name"],
        )

        # Ensure output dir exists
        output_dir = instance.data["outputDir"]
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir)

        # Prepare for extend frames when enabled
        copy_resources = []
        extend_frames = data.get("extendFrames", False)
        if extend_frames:
            # Collect the frames to copy to extend the frames
            # and set the start frame and end frame to include the
            # extended frames
            new_start, new_end, copy_resources = self.extend_frames(instance, job)
            instance.data["startFrame"] = new_start
            instance.data["endFrame"] = new_end

        # Generate publish metadata file for the standalone publish job
        publish_metadata = compute_publish_from_instance(instance)
        metadata_filename = "{}_metadata.json".format(subset)
        metadata_path = os.path.join(output_dir, metadata_filename)
        with open(metadata_path, "w") as f:
            json.dump(publish_metadata, f, indent=4, sort_keys=True)

        # Generate the payload for Deadline submission
        payload = {
            "JobInfo": {
                "Plugin": "Python",
                "BatchName": job["Props"]["Batch"],
                "Priority": job["Props"]["Pri"],        # priority
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

        # Avoid copied pools and remove secondary pool
        payload["JobInfo"]["Pool"] = "none"
        payload["JobInfo"].pop("SecondaryPool", None)

        # Force "publish" group
        payload["JobInfo"]["Group"] = "publish"

        self.log.info("Submitting..")
        self.log.debug(json.dumps(payload, indent=4, sort_keys=True))

        url = "{}/api/jobs".format(AVALON_DEADLINE)
        response = requests.post(url, json=payload)
        if not response.ok:
            raise Exception(response.text)

        # Copy files from previous publish if extendFrame is True
        if copy_resources:
            self.log.info("Preparing to copy for extend frames..")
            dest_path = data["outputDir"]
            for source in copy_resources:
                src_file = os.path.basename(source)
                dest = os.path.join(dest_path, src_file)
                speedcopy.copyfile(source, dest)

            self.log.info("Finished copying %i files" % len(copy_resources))

    def extend_frames(self, instance, job):

        data = instance.data
        family = "colorbleed.imagesequence"
        override = data["overrideExistingFrame"]

        out_file = job.get("OutFile")
        if not out_file:
            raise RuntimeError("OutFile not found in render job!")

        extension = os.path.splitext(out_file[0])[1]
        _ext = extension[1:]

        start = instance.data["startFrame"]
        end = instance.data["endFrame"]

        # Frame comparison
        prev_start = None
        prev_end = None
        resource_range = range(int(start), int(end) + 1)

        # Gather all the subset files
        resources = []
        for subset_name in instance.data["renderSubsets"].keys():
            version = get_latest_version(asset_name=data["asset"],
                                         subset_name=subset_name,
                                         family=family)

            # Set prev start / end frames for comparison
            if not prev_start and not prev_end:
                prev_start = version["data"]["startFrame"]
                prev_end = version["data"]["endFrame"]

            subset_resources = get_resources(version, _ext)
            resource_files = get_resource_files(subset_resources,
                                                resource_range,
                                                override)

            resources.extend(resource_files)

        updated_start = min(start, prev_start)
        updated_end = max(end, prev_end)

        # Update metadata and instance start / end frame
        self.log.info("Updating start and end frame: "
                      "{} - {}".format(updated_start, updated_end))

        return updated_start, updated_end, resources
