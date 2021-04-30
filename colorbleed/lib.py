import os
import re
import sys
import errno
import logging
import importlib
import itertools

from .vendor import pather
from .vendor.pather.error import ParseError
from .vendor import speedcopy

import avalon.io as io
import avalon.api
from avalon import schema
from avalon.vendor import six

import pyblish.util

log = logging.getLogger(__name__)


def pairwise(iterable):
    """s -> (s0,s1), (s2,s3), (s4, s5), ..."""
    a = iter(iterable)
    return itertools.izip(a, a)


def grouper(iterable, n, fillvalue=None):
    """Collect data into fixed-length chunks or blocks

    Examples:
        grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx

    """

    args = [iter(iterable)] * n
    return itertools.izip_longest(fillvalue=fillvalue, *args)


def is_latest(representation):
    """Return whether the representation is from latest version

    Args:
        representation (dict): The representation document from the database.

    Returns:
        bool: Whether the representation is of latest version.

    """

    version = io.find_one({"_id": representation['parent']})

    # Get highest version under the parent
    highest_version = io.find_one({
        "type": "version",
        "parent": version["parent"]
    }, sort=[("name", -1)], projection={"name": True})

    if version['name'] == highest_version['name']:
        return True
    else:
        return False


def any_outdated():
    """Return whether the current scene has any outdated content"""

    checked = set()
    host = avalon.api.registered_host()
    for container in host.ls():
        representation = container['representation']
        if representation in checked:
            continue

        representation_doc = io.find_one({"_id": io.ObjectId(representation),
                                          "type": "representation"},
                                         projection={"parent": True})
        if representation_doc and not is_latest(representation_doc):
            return True
        elif not representation_doc:
            log.debug("Container '{objectName}' has an invalid "
                      "representation, it is missing in the "
                      "database".format(**container))

        checked.add(representation)
    return False


def update_task_from_path(path):
    """Update the context using the current scene state.

    When no changes to the context it will not trigger an update.
    When the context for a file could not be parsed an error is logged but not
    raised.

    """
    if not path:
        log.warning("Can't update the current task. Scene is not saved.")
        return

    # Find the current context from the filename
    project = io.find_one({"type": "project"},
                          projection={"config.template.work": True})
    template = project['config']['template']['work']
    # Force to use the registered to root to avoid using wrong paths
    template = pather.format(template, {"root": avalon.api.registered_root()})
    try:
        context = pather.parse(template, path)
    except ParseError:
        log.error("Can't update the current task. Unable to parse the "
                  "task for: %s (pattern: %s)", path, template)
        return

    # Find the changes between current Session and the path's context.
    current = {
        "asset": avalon.api.Session["AVALON_ASSET"],
        "task": avalon.api.Session["AVALON_TASK"],
        "app": avalon.api.Session["AVALON_APP"]
    }
    changes = {key: context[key] for key, current_value in current.items()
               if context[key] != current_value}

    if changes:
        log.info("Updating work task to: %s", context)
        avalon.api.update_current_task(**changes)


def _rreplace(s, a, b, n=1):
    """Replace a with b in string s from right side n times"""
    return b.join(s.rsplit(a, n))


def version_up(filepath):
    """Version up filepath to a new non-existing version.

    Parses for a version identifier like `_v001` or `.v001`
    When no version present _v001 is appended as suffix.

    Returns:
        str: filepath with increased version number

    """

    dirname = os.path.dirname(filepath)
    basename, ext = os.path.splitext(os.path.basename(filepath))

    regex = "[._]v\d+"
    matches = re.findall(regex, str(basename), re.IGNORECASE)
    if not matches:
        log.info("Creating version...")
        new_label = "_v{version:03d}".format(version=1)
        new_basename = "{}{}".format(basename, new_label)
    else:
        label = matches[-1]
        version = re.search("\d+", label).group()
        padding = len(version)

        new_version = int(version) + 1
        new_version = '{version:0{padding}d}'.format(version=new_version,
                                                     padding=padding)
        new_label = label.replace(version, new_version, 1)
        new_basename = _rreplace(basename, label, new_label)

    new_filename = "{}{}".format(new_basename, ext)
    new_filename = os.path.join(dirname, new_filename)
    new_filename = os.path.normpath(new_filename)

    if new_filename == filepath:
        raise RuntimeError("Created path is the same as current file,"
                           "this is a bug")

    if os.path.exists(new_filename):
        log.info("Skipping existing version %s" % new_label)
        return version_up(new_filename)

    log.info("New version %s" % new_label)
    return new_filename


def switch_item(container,
                asset_name=None,
                subset_name=None,
                representation_name=None):
    """Switch container asset, subset or representation of a container by name.

    It'll always switch to the latest version - of course a different
    approach could be implemented.

    Args:
        container (dict): data of the item to switch with
        asset_name (str): name of the asset
        subset_name (str): name of the subset
        representation_name (str): name of the representation

    Returns:
        dict

    """

    if all(not x for x in [asset_name, subset_name, representation_name]):
        raise ValueError("Must have at least one change provided to switch.")

    # Collect any of current asset, subset and representation if not provided
    # so we can use the original name from those.
    if any(not x for x in [asset_name, subset_name, representation_name]):
        _id = io.ObjectId(container["representation"])
        representation = io.find_one({"type": "representation", "_id": _id})
        version, subset, asset, project = io.parenthood(representation)

        if asset_name is None:
            asset_name = asset["name"]

        if subset_name is None:
            subset_name = subset["name"]

        if representation_name is None:
            representation_name = representation["name"]

    # Find the new one
    asset = io.find_one({"name": asset_name, "type": "asset"})
    assert asset, ("Could not find asset in the database with the name "
                   "'%s'" % asset_name)

    subset = io.find_one({"name": subset_name,
                          "type": "subset",
                          "parent": asset["_id"]})
    assert subset, ("Could not find subset in the database with the name "
                    "'%s'" % subset_name)

    version = io.find_one({"type": "version",
                           "parent": subset["_id"]},
                          sort=[('name', -1)])

    assert version, "Could not find a version for {}.{}".format(
        asset_name, subset_name
    )

    representation = io.find_one({"name": representation_name,
                                  "type": "representation",
                                  "parent": version["_id"]})

    assert representation, ("Could not find representation in the database with"
                            " the name '%s'" % representation_name)

    avalon.api.switch(container, representation)

    return representation


def _get_host_name():

    _host = avalon.api.registered_host()
    # This covers nested module name like avalon.maya
    return _host.__name__.rsplit(".", 1)[-1]


def collect_container_metadata(container):
    """Add additional data based on the current host

    If the host application's lib module does not have a function to inject
    additional data it will return the input container

    Args:
        container (dict): collection if representation data in host

    Returns:
        generator
    """
    # TODO: Improve method of getting the host lib module
    host_name = _get_host_name()
    package_name = "colorbleed.{}.lib".format(host_name)
    hostlib = importlib.import_module(package_name)

    if not hasattr(hostlib, "get_additional_data"):
        return {}

    return hostlib.get_additional_data(container)


def get_asset_fps():
    """Returns project's FPS, if not found will return 25 by default

    Returns:
        int, float

    """

    key = "fps"

    # FPS from asset data (if set)
    asset_data = get_asset_data()
    if key in asset_data:
        return asset_data[key]

    # FPS from project data (if set)
    project_data = get_project_data()
    if key in project_data:
        return project_data[key]

    # Fallback to 25 FPS
    return 25.0


def get_project_data():
    """Get the data of the current project

    The data of the project can contain things like:
        resolution
        fps
        renderer

    Returns:
        dict:

    """

    project_name = io.active_project()
    project = io.find_one({"name": project_name,
                           "type": "project"},
                          projection={"data": True})

    data = project.get("data", {})

    return data


def get_asset_data(asset=None):
    """Get the data from the current asset

    Args:
        asset(str, Optional): name of the asset, eg:

    Returns:
        dict
    """

    asset_name = asset or avalon.api.Session["AVALON_ASSET"]
    document = io.find_one({"name": asset_name,
                            "type": "asset"})

    data = document.get("data", {})

    return data


def publish_remote():
    """Perform a publish without pyblish GUI that will sys.exit on errors.

    This will:
        - `sys.exit(1)` on nothing being collected
        - `sys.exit(2)` on errors during publish

    Note: This function assumes Avalon has been installed prior to this.
          As such it does *not* trigger avalon.api.install().

    """
    print("Starting pyblish.util.pyblish()..")
    context = pyblish.util.publish()
    print("Finished pyblish.util.publish(), checking for errors..")

    if not context:
        log.warning("Fatal Error: Nothing collected.")
        sys.exit(1)

    # Collect errors, {plugin name: error}
    error_results = [r for r in context.data["results"] if r["error"]]

    if error_results:
        error_format = "Failed {plugin.__name__}: {error} -- {error.traceback}"
        for result in error_results:
            log.error(error_format.format(**result))

        log.error("Fatal Error: Errors occurred during publish, see log..")
        sys.exit(2)

    print("All good. Success!")


class Integrator(object):
    """Integrate the instance into the database and to published location.

    This will register the new publish version into the database and generate
    the destination location with the files on the server.

    Integration will only happen when *NO* errors occurred whatsoever during
    the publish, otherwise it will abort with "Atomicity not held"

    Required instance.data:
        subset (str): The subset name to publish.
        families or family (list or str): List of families to publish.
            The single "family" is deprecated and remains for backwards
            compatibility. Note that the integrated family can be overridden
            by `publishFamilies` which will result in explicitly matching only
            those families.
        stagingDir (str): Staging path directory.
        files (list): relative filenames in staging dir that
            will be transferred along with the publish. The extension of the
            file will be the resulting representation (os.path.splitext)
            without the dot (.) prefix.

    Required instance.context.data:
        time (str): Current time for publish creation, see pyblish.api.time()
        user (str): Current user name creating this publish.
        currentFile (str): Path to current working file.

    Optional instance.data:

        asset (str): The asset name. When not provided
            api.Session["AVALON_ASSET"] is used.

        transfers (list): List of source to destination file transfer paths.
            These should be full filepaths for both source and destination.
            This is optional because "files" and "stagingDir" are provided and
            those will result in transfers too.

        assumedTemplateData (dict): Destination data collected
            by CollectAssumedDestination collector. Used to validate the
            collected information is still correct at this time of publish.

        publishFamilies (list): Output avalon families.
            This overrides "families" for the publish so that the integrated
            family can differ from the families set to detect Pyblish plugins.

        inputs (list): The input representations used in creation of this
            publish. These should be Avalon representation database ids.

    """

    def __init__(self):
        self.log = logging.getLogger("colorbleed.lib.Integrator")

    def process(self, instance):
        self.register(instance)
        self.integrate(instance.data["transfers"])

    def register(self, instance):

        context = instance.context
        # Atomicity
        # Guarantee atomic publishes - each asset contains
        # an identical set of members.
        assert all(result["success"] for result in context.data["results"]), (
            "Atomicity not held, aborting.")

        # Assemble
        assert "files" in instance.data, "No files data found.."
        assert any(instance.data["files"]), "No files found to transfer.."
        stagingdir = instance.data.get("stagingDir")
        assert stagingdir, ("Incomplete instance \"%s\": "
                            "Missing reference to staging area." % instance)
        self.log.debug("Found staging directory @ %s" % stagingdir)

        # Required environment variables
        PROJECT = avalon.api.Session["AVALON_PROJECT"]
        ASSET = (instance.data.get("asset") or
                 avalon.api.Session["AVALON_ASSET"])
        LOCATION = avalon.api.Session["AVALON_LOCATION"]

        project = io.find_one({"name": PROJECT,
                               "type": "project"},
                              projection={"name": True,
                                          "config.template.publish": True})
        assert project, "Could not find project '%s'" % PROJECT

        asset = io.find_one({"type": "asset",
                             "name": ASSET,
                             "parent": project["_id"]})
        assert asset, "Could not find asset '%s'" % ASSET

        subset, is_new_subset = self.get_or_create_subset(asset, instance)

        version = self.create_version(instance=instance,
                                      subset=subset,
                                      is_new_subset=is_new_subset,
                                      locations=[LOCATION])

        representations = self.create_representations(
            instance=instance,
            stagingdir=stagingdir,
            project=project,
            asset=asset,
            subset=subset,
            version=version
        )

        # Insert all documents into the database and set the parent ids
        if is_new_subset:
            self.log.debug("Registering subset..")
            io.insert_one(subset)

        self.log.debug("Registering version..")
        io.insert_one(version)

        self.log.info("Registering %s representations" % len(representations))
        io.insert_many(representations)

    def integrate(self, transfers):
        """Copy the files

        Args:
            transfers (list): The source to destination paths to integrate.
        """

        for src, dest in transfers:
            self.log.info("Copying file {} -> {}".format(src, dest))
            self.copy_file(src, dest)

    def copy_file(self, src, dst):
        """Copy given source to destination

        Arguments:
            src (str): the source file which needs to be copied
            dst (str): the destination of the file
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

        subset_name = instance.data["subset"]
        subset = io.find_one({"type": "subset",
                              "parent": asset["_id"],
                              "name": subset_name})
        if subset:
            return subset, False

        # Define a new subset if it didn't exist yet.
        self.log.info("Subset '%s' not found, creating.." % subset_name)
        families = self._get_families(instance)

        subset = {
            "_id": io.ObjectId(),
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
            assert isinstance(group, str), "subsetGroup data must be string"
            subset["data"]["subsetGroup"] = group

        # Validate schema
        schema.validate(subset)

        return subset, True

    def create_version(self,
                       instance,
                       subset,
                       is_new_subset,
                       locations):
        """ Copy given source to destination

        Args:
            instance: the current instance being published
            subset (dict): the registered subset of the asset
            is_new_subset (bool): Whether the Subset will be newly created.
                When True we can skip checking for existing versions.
            locations (list): the currently registered locations

        Returns:
            dict: collection of data to create a version
        """

        # Get next version
        next_version = 1
        if not is_new_subset:
            latest_version = io.find_one({"type": "version",
                                          "parent": subset["_id"]},
                                         {"name": True},
                                         sort=[("name", -1)])
            if latest_version is not None:
                next_version += latest_version["name"]

        # If assumed template data was collected then verify it matches version
        assumed_data = instance.data.get("assumedTemplateData")
        if assumed_data:
            self.log.debug("Verifying version from assumed destination..")
            assumed_version = assumed_data["version"]
            if assumed_version != next_version:
                raise AttributeError("Assumed version 'v{0:03d}' does not "
                                     "match next version in database "
                                     "('v{1:03d}')".format(assumed_version,
                                                           next_version))
        self.log.debug("Next version: v{0:03d}".format(next_version))

        version = {
            "_id": io.ObjectId(),
            "schema": "avalon-core:version-3.0",
            "type": "version",
            "parent": subset["_id"],
            "name": next_version,
            "locations": locations,
            "data": self._get_version_data(instance)
        }

        # Backwards compatibility for when family was still stored on the
        # version as opposed to the subset. See getavalon/core#443.
        if subset["schema"] == "avalon-core:subset-2.0":
            # Stick to older version schema and add families into version
            self.log.debug("Falling back to older version schema to match "
                           "subset schema 'avalon-core:subset-2.0'")
            version["schema"] = "avalon-core:version-2.0"
            version["data"]["families"] = self._get_families(instance)

        schema.validate(version)
        return version

    def create_representations(self,
                               instance,
                               stagingdir,
                               project,
                               asset,
                               subset,
                               version):

        silo = asset.get("silo", None)

        # Define staging directory to publish transfers and its representations
        root = avalon.api.registered_root()
        template_data = {"root": root,
                         "project": project["name"],
                         "asset": asset["name"],
                         "subset": subset["name"],
                         "version": version["name"]}
        if silo:
            template_data["silo"] = silo

        template_publish = project["config"]["template"]["publish"]

        # Append transfers to any that are already on the Instance
        transfers = instance.data.get("transfers", list())

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

                    transfers.append([src, dst])

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

                transfers.append([src, dst])

            representation = {
                "schema": "avalon-core:representation-2.0",
                "type": "representation",
                "parent": version["_id"],
                "name": ext[1:],
                "data": {},
                "dependencies": instance.data.get("dependencies", "").split(),

                # Imprint shortcut to context
                # for performance reasons.
                "context": {
                    "project": project["name"],
                    "asset": asset["name"],
                    "subset": subset["name"],
                    "version": version["name"],
                    "representation": ext[1:]
                }
            }

            if silo:
                representation["context"]["silo"] = silo

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

            schema.validate(representation)
            representations.append(representation)

        instance.data["transfers"] = transfers

        return representations

    def _get_version_data(self, instance):
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

        try:
            # create relative source in project root for DB
            relative_path = os.path.relpath(current_file,
                                            avalon.api.registered_root())
            source = os.path.join("{root}", relative_path)
        except ValueError:
            # store full path if not on the same drive as project root
            source = current_file.replace("\\", "/")

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

        # Allow custom publish families to be defined when they
        # need to be different from the Pyblish families. E.g.
        # a specific family to be triggered by specific Pyblish plug-ins
        if "publishFamilies" in instance.data:
            return instance.data["publishFamilies"]

        # Get families for the subset
        families = instance.data.get("families", list())

        # Backwards compatibility for primary family stored in instance.
        primary_family = instance.data.get("family", None)
        if primary_family and primary_family not in families:
            families.insert(0, primary_family)

        assert families, "Instance must have at least a single family"

        return families


def clean_filename(fname, replace=None):
    r"""Remove invalid characters from filename.

    Do not use this on a full filepath but only on the filename as it will
    also strip / or \ characters.

    Args:
        fname (str): Filename (not full filepath)
        replace (str, optional): Optional character to replace invalid
            characters with. Defaults to None stripping the characters.

    """
    invalid = r'\/*?:"<>|'
    replace = ord(replace) if replace else None
    fname = six.text_type(fname)        # ensure unicode in py2, str in py3
    return fname.translate({ord(char): replace for char in invalid})
