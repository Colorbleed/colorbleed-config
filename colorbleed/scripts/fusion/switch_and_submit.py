import os
import re
import sys
import logging

# Pipeline imports
from avalon import api, io, pipeline
import avalon.fusion

# Config imports
import colorbleed.lib as colorbleed
import colorbleed.fusion.lib as fusion_lib

log = logging.getLogger("Update Slap Comp")

self = sys.modules[__name__]
self._project = None

error_format = "Failed {plugin.__name__}: {error} -- {error.traceback}"


def get_fusion_instance():
    """Try to get an instance of Fusion"""
    fusion = getattr(sys.modules["__main__"], "fusion", None)
    if fusion is None:
        try:
            # Support for FuScript.exe, BlackmagicFusion module for py2 only
            import BlackmagicFusion as bmf
            fusion = bmf.scriptapp("Fusion", "localhost", 2)
        except ImportError:
            raise RuntimeError("Could not find a Fusion instance")
    return fusion


def format_version_folder(folder):
    """Format a version folder based on the filepath

    Assumption here is made that, if the path does not exists the folder
    will be "v001"

    Args:
        folder: file path to a folder

    Returns:
        str: new version folder name
    """

    version_int = 1
    if os.path.isdir(folder):
        re_version = re.compile("v\d+")
        versions = [i for i in os.listdir(folder) if re_version.match(i)
                    and os.path.isdir(os.path.join(folder, i))]
        if versions:
            # ensure the "v" is not included and convert to ints
            int_versions = [int(v[1:]) for v in versions]
            version_int += max(int_versions)

    return "v{:03d}".format(version_int)


def format_filepath(session):

    project = session["AVALON_PROJECT"]
    asset = session["AVALON_ASSET"]

    # Save updated slap comp
    work_path = get_work_folder(session)
    walk_to_dir = os.path.join(work_path, "scenes", "slapcomp")
    slapcomp_dir = os.path.abspath(walk_to_dir)

    # Ensure destination exists
    if not os.path.isdir(slapcomp_dir):
        log.warning("Folder did not exist, creating folder structure")
        os.makedirs(slapcomp_dir)

    # Compute output path
    new_filename = "{}_{}_slapcomp_v001.comp".format(project, asset)
    new_filepath = os.path.join(slapcomp_dir, new_filename)

    # Create new unqiue filepath
    if os.path.exists(new_filepath):
        new_filepath = colorbleed.version_up(new_filepath)

    return new_filepath


def get_work_folder(session):
    """Convenience function to get the work folder path of the current asset"""

    # Get new filename, create path based on asset and work template
    template_work = self._project["config"]["template"]["work"]
    work_path = pipeline._format_work_template(template_work, session)

    return os.path.normpath(work_path)


def update_savers(comp, session):
    """Update all savers of the current comp to ensure the output is correct

    Args:
        comp (object): current comp instance
        session (dict): the current Avalon session

    Returns:
         None
    """

    new_work = get_work_folder(session)
    renders = os.path.join(new_work, "renders")
    version_folder = format_version_folder(renders)
    renders_version = os.path.join(renders, version_folder)

    comp.Print("New renders to: %s\n" % renders)

    with avalon.fusion.comp_lock_and_undo_chunk(comp):
        savers = comp.GetToolList(False, "Saver").values()
        for saver in savers:
            filepath = saver.GetAttrs("TOOLST_Clip_Name")[1.0]
            filename = os.path.basename(filepath)
            new_path = os.path.join(renders_version, filename)
            saver["Clip"] = new_path


def update_frame_range(comp, representations):
    """Update the frame range of the comp and render length

    The start and end frame are based on the lowest start frame and the highest
    end frame

    Args:
        comp (object): current focused comp
        representations (list) collection of dicts

    Returns:
        None

    """

    version_ids = [r["parent"] for r in representations]
    versions = io.find({"type": "version", "_id": {"$in": version_ids}})
    versions = list(versions)

    start = min(v["data"]["startFrame"] for v in versions)
    end = max(v["data"]["endFrame"] for v in versions)

    fusion_lib.update_frame_range(start, end, comp=comp)


def switch(file_path=None, asset_name=None, new=True, deadline=True):
    """Switch the current containers of the file to the other asset (shot)

    Args:
        file_path (str): file path of the comp file
        asset_name (str): name of the asset (shot)
        new (bool): Save updated comp under a different name
        deadline (bool): if set to true

    Returns:
        comp path (str): new filepath of the updated comp

    """

    assert asset_name, "Function requires at least an asset name"

    # Ensure filename is absolute
    if file_path:
        file_path = os.path.abspath(file_path)

    api.install(avalon.fusion)
    host = api.registered_host()

    # Get current project
    self._project = io.find_one({"type": "project",
                                 "name": api.Session["AVALON_PROJECT"]})

    # Assert asset name exists
    # It is better to do this here then to wait till switch_shot does it
    asset = io.find_one({"type": "asset", "name": asset_name})
    assert asset, "Could not find '%s' in the database" % asset_name

    if not file_path:
        # Assuming we use the current open comp
        current_comp = avalon.fusion.get_current_comp()
        assert current_comp is not None, "Could not find current comp"
        file_path = current_comp.GetAttrs("COMPS_FileName")
    else:
        fusion = get_fusion_instance()
        current_comp = fusion.LoadComp(file_path)
        assert current_comp is not None, ("Fusion could not load '%s'"
                                          % file_path)

    containers = list(host.ls())
    assert containers, "Nothing to update"

    representations = []
    for container in containers:
        try:
            representation = colorbleed.switch_item(container,
                                                    asset_name=asset_name)
            representations.append(representation)
            current_comp.Print(str(representation["_id"]) + "\n")
        except Exception as e:
            current_comp.Print("Error in switching! %s\n" % e.message)

    message = "Switched %i Loaders of the %i\n" % (len(representations),
                                                   len(containers))
    current_comp.Print(message)

    # Build the session to switch to
    switch_to_session = api.Session.copy()
    switch_to_session["AVALON_ASSET"] = asset['name']

    if new:
        comp_path = format_filepath(switch_to_session)

        # Update savers output based on new session
        update_savers(current_comp, switch_to_session)
    else:
        comp_path = colorbleed.version_up(file_path)

    current_comp.Print("\nNew path: %s" % comp_path)
    current_comp.Print("\nUpdating frame range ..")
    update_frame_range(current_comp, representations)

    # Save changes
    current_comp.Save(comp_path)

    if deadline:
        # Update session with correct asset name and comp path
        api.Session.update(switch_to_session)

        # Set render mode to deadline
        current_comp.SetData("colorbleed.rendermode", "deadline")

        # Run publisher
        context = api.publish()
        if not context:
            log.warning("Nothing collected.")
            sys.exit(1)

        # Collect errors, {plugin name: error}, if any
        error_results = [r for r in context.data["results"] if r["error"]]
        if error_results:
            log.error("Errors occurred ...")
            for result in error_results:
                log.error(error_format.format(**result))
            sys.exit(2)

    return current_comp
