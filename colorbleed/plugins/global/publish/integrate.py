import os
import copy
import logging
import shutil

import errno
import pyblish.api
from avalon import api, io, schema
import colorbleed.vendor.speedcopy as speedcopy


log = logging.getLogger(__name__)


class IntegrateAsset(pyblish.api.InstancePlugin):
    """Integrate the instance into the database and to published location.

    This will register the new publish version into the database and generate
    the destination location with the files on the server.

    Integration will only happen when *NO* errors occurred whatsoever during
    the publish, otherwise it will abort with "Atomicity not held"

    The files that will be transferred are:
        - instance.data["files"]: relative filenames in staging dir that will
            be transferred along with the publish. The extension of the file
            will be the resulting representation (os.path.splitext) without
            the dot (.) prefix.
        - instance.data["transfer"]: straight per file copy src -> dst

    Required inputs:
        instance.data["asset"]
        instance.data["subset"]
        instance.data["families"] or instance.data["family"] (deprecated)
        instance.data["stagingDir"]
        instance.data["files"]
        instance.data["transfers"]
        instance.context.data["time"]
        instance.context.data["user"]
        instance.context.data["currentFile"]

    Optional inputs:
        instance.data["assumedTemplateData"]

    """

    label = "Integrate Asset"
    order = pyblish.api.IntegratorOrder
    families = ["colorbleed.animation",
                "colorbleed.camera",
                "colorbleed.fbx",
                "colorbleed.imagesequence",
                "colorbleed.look",
                "colorbleed.mayaAscii",
                "colorbleed.model",
                "colorbleed.pointcache",
                "colorbleed.vdbcache",
                "colorbleed.setdress",
                "colorbleed.rig",
                "colorbleed.vrayproxy",
                "colorbleed.yetiRig",
                "colorbleed.yeticache",
                "colorbleed.review",
                "colorbleed.usd",
                # We don't actually integrate to colorbleed.usd.bootstrap
                # because on extraction we swap the family to colorbleed.usd.
                # However without this the integrator would not be loaded if
                # there was no colorbleed.usd instance to begin with.
                "colorbleed.usd.bootstrap"
                ]
    targets = ["local"]

    def process(self, instance):

        self.register(instance)

        self.log.info("Integrating Asset in to the database ...")
        self.integrate(instance)

    def register(self, instance):

        # Required environment variables
        PROJECT = api.Session["AVALON_PROJECT"]
        ASSET = instance.data.get("asset") or api.Session["AVALON_ASSET"]
        LOCATION = api.Session["AVALON_LOCATION"]

        context = instance.context
        # Atomicity
        #
        # Guarantee atomic publishes - each asset contains
        # an identical set of members.
        #     __
        #    /     o
        #   /       \
        #  |    o    |
        #   \       /
        #    o   __/
        #
        assert all(result["success"] for result in context.data["results"]), (
            "Atomicity not held, aborting.")

        # Assemble
        #
        #       |
        #       v
        #  --->   <----
        #       ^
        #       |
        #
        stagingdir = instance.data.get("stagingDir")
        assert stagingdir, ("Incomplete instance \"%s\": "
                            "Missing reference to staging area." % instance)

        # extra check if stagingDir actually exists and is available
        self.log.debug("Establishing staging directory @ %s" % stagingdir)

        project = io.find_one({"type": "project"},
                              projection={"config.template.publish": True})

        asset = io.find_one({"type": "asset",
                             "name": ASSET,
                             "parent": project["_id"]})

        assert all([project, asset]), ("Could not find current project or "
                                       "asset '%s'" % ASSET)

        subset = self.get_or_create_subset(asset, instance)

        # get next version
        latest_version = io.find_one({"type": "version",
                                      "parent": subset["_id"]},
                                     {"name": True},
                                     sort=[("name", -1)])

        next_version = 1
        if latest_version is not None:
            next_version += latest_version["name"]

        assumed_data = instance.data.get("assumedTemplateData")
        if assumed_data:
            self.log.info("Verifying version from assumed destination")
            assumed_version = assumed_data["version"]
            if assumed_version != next_version:
                raise AttributeError("Assumed version 'v{0:03d}' does not "
                                     "match next version in database "
                                     "('v{1:03d}')".format(assumed_version,
                                                           next_version))

        self.log.debug("Next version: v{0:03d}".format(next_version))

        version = self.create_version(instance=instance,
                                      subset=subset,
                                      version_number=next_version,
                                      locations=[LOCATION])

        schema.validate(version)
        self.log.debug("Creating version ...")
        version_id = io.insert_one(version).inserted_id

        # Write to disk
        #          _
        #         | |
        #        _| |_
        #    ____\   /
        #   |\    \ / \
        #   \ \    v   \
        #    \ \________.
        #     \|________|
        #
        root = api.registered_root()
        template_data = {"root": root,
                         "project": PROJECT,
                         "silo": asset['silo'],
                         "asset": ASSET,
                         "subset": subset["name"],
                         "version": version["name"]}

        template_publish = project["config"]["template"]["publish"]

        # Find the representations to transfer amongst the files
        # Each should be a single representation (as such, a single extension)
        representations = []

        for files in instance.data["files"]:

            # Collection
            #   _______
            #  |______|\
            # |      |\|
            # |       ||
            # |       ||
            # |       ||
            # |_______|
            #
            if isinstance(files, list):
                collection = files
                # Assert that each member has identical suffix
                _, ext = os.path.splitext(collection[0])
                assert all(ext == os.path.splitext(name)[1]
                           for name in collection), (
                    "Files had varying suffixes, this is a bug"
                )

                assert not any(os.path.isabs(name) for name in collection)

                template_data["representation"] = ext[1:]

                for fname in collection:

                    src = os.path.join(stagingdir, fname)
                    dst = os.path.join(
                        template_publish.format(**template_data),
                        fname
                    )

                    instance.data["transfers"].append([src, dst])

            else:
                # Single file
                #  _______
                # |      |\
                # |       |
                # |       |
                # |       |
                # |_______|
                #
                fname = files
                assert not os.path.isabs(fname), (
                    "Given file name is a full path"
                )
                _, ext = os.path.splitext(fname)

                template_data["representation"] = ext[1:]

                src = os.path.join(stagingdir, fname)
                dst = template_publish.format(**template_data)

                instance.data["transfers"].append([src, dst])

            representation = {
                "schema": "avalon-core:representation-2.0",
                "type": "representation",
                "parent": version_id,
                "name": ext[1:],
                "data": {},
                "dependencies": instance.data.get("dependencies", "").split(),

                # Imprint shortcut to context
                # for performance reasons.
                "context": {
                    "project": PROJECT,
                    "asset": ASSET,
                    "silo": asset['silo'],
                    "subset": subset["name"],
                    "version": version["name"],
                    "representation": ext[1:]
                }
            }

            # Insert dependencies data when present and
            # containing at least some content
            inputs = instance.data.get("inputs", None)
            if inputs:
                # Ensure the inputs are what we expect of them, list of ids
                # This is a bit verbose and should be validated earlier,
                # however this is purely intended to ensure this newly
                # supported input tracking is consistently created for now.
                # todo(roy): Remove these redundant assertions
                assert isinstance(inputs, (list, tuple))
                inputs = [io.ObjectId(x) for x in inputs]
                representation["data"]["inputs"] = inputs

            representations.append(representation)

        # Validate all representations
        for representation in representations:
            schema.validate(representation)

        self.log.info("Registering %s representations" % len(representations))
        io.insert_many(representations)

    def integrate(self, instance):
        """Move the files

        Through `instance.data["transfers"]`

        Args:
            instance: the instance to integrate
        """

        transfers = instance.data["transfers"]

        for src, dest in transfers:
            self.log.info("Copying file .. {} -> {}".format(src, dest))
            self.copy_file(src, dest)

    def copy_file(self, src, dst):
        """Copy given source to destination

        Arguments:
            src (str): the source file which needs to be copied
            dst (str): the destination of the sourc file
        Returns:
            None
        """

        dirname = os.path.dirname(dst)
        try:
            os.makedirs(dirname)
        except OSError as e:
            if e.errno == errno.EEXIST:
                pass
            else:
                self.log.critical("An unexpected error occurred.")
                raise

        speedcopy.copyfile(src, dst)

    def get_or_create_subset(self, asset, instance):

        subset = io.find_one({"type": "subset",
                              "parent": asset["_id"],
                              "name": instance.data["subset"]})

        if subset is None:
            # Create subset if it didn't exist yet.
            subset_name = instance.data["subset"]
            self.log.info("Subset '%s' not found, creating.." % subset_name)
            families = self._get_families(instance)

            subset = {
                "schema": "avalon-core:subset-3.0",
                "type": "subset",
                "name": subset_name,
                "data": {
                    "families": families
                },
                "parent": asset["_id"]
            }

            group = instance.data.get("subsetGroup")
            if group:
                assert isinstance(group, str), (
                    "subsetGroup data must be string"
                )
                subset["data"]["subsetGroup"] = group

            # Validate schema
            schema.validate(subset)

            _id = io.insert_one(subset).inserted_id

            # Optimization: Instead of querying the subset again, just add
            # "_id" into the data to avoid a database query.
            subset["_id"] = _id

        return subset

    def create_version(self,
                       instance,
                       subset,
                       version_number,
                       locations):
        """ Copy given source to destination

        Args:
            instance: the current instance being published
            subset (dict): the registered subset of the asset
            version_number (int): the version number
            locations (list): the currently registered locations

        Returns:
            dict: collection of data to create a version
        """

        data = self.create_version_data(instance)

        # Imprint currently registered location
        version_locations = [location for location in locations if
                             location is not None]

        version = {
            "schema": "avalon-core:version-3.0",
            "type": "version",
            "parent": subset["_id"],
            "name": version_number,
            "locations": version_locations,
            "data": data
        }

        # Backwards compatibility for when family was still stored on the
        # version as opposed to the subset. See getavalon/core#443.
        if subset["schema"] == "avalon-core:subset-2.0":
            # Stick to older version schema and add families into version
            self.log.debug("Falling back to older version schema to match "
                           "subset schema 'avalon-core:subset-2.0'")
            version["schema"] = "avalon-core:version-2.0"
            version["data"]["families"] = self._get_families(instance)

        return version

    def create_version_data(self, instance):
        """Create the data for the version

        Args:
            instance: the current instance being published

        Returns:
            dict: the required information with instance.data as key
        """

        context = instance.context

        # Allow current file to also be set per instance if they have the data
        # otherwise it *must* be present in the context. This way we can e.g.
        # per image sequence instance store the original source location.
        current_file = instance.data.get("currentFile", None)
        if current_file is None:
            current_file = context.data["currentFile"]

        # create relative source path for DB
        relative_path = os.path.relpath(current_file,
                                        api.registered_root())
        source = os.path.join("{root}", relative_path).replace("\\", "/")

        version_data = {"time": context.data["time"],
                        "author": context.data["user"],
                        "source": source,
                        "comment": context.data.get("comment"),
                        "machine": context.data.get("machine"),
                        "fps": context.data.get("fps")}

        # Include optional data if present in
        optionals = ["startFrame", "endFrame", "step", "handles"]
        for key in optionals:
            if key in instance.data:
                version_data[key] = instance.data[key]

        return version_data

    def _get_families(self, instance):
        """Helper function to get the families from instance data"""

        # Get families for the subset
        families = instance.data.get("families", list())

        # Backwards compatibility for primary family stored in instance.
        primary_family = instance.data.get("family", None)
        if primary_family and primary_family not in families:
            families.insert(0, primary_family)

        assert families, "Instance must have at least a single family"

        return families
