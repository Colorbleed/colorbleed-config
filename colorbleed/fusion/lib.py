import os
import re
import sys
import logging

import avalon.fusion
from avalon import api, io, pipeline

import colorbleed.lib as colorbleed

self = sys.modules[__name__]
self._project = None

log = logging.getLogger(__name__)


def update_frame_range(start, end, comp=None, set_render_range=True):
    """Set Fusion comp's start and end frame range

    Args:
        start (float, int): start frame
        end (float, int): end frame
        comp (object, Optional): comp object from fusion
        set_render_range (bool, Optional): When True this will also set the
            composition's render start and end frame.

    Returns:
        None

    """

    if not comp:
        comp = avalon.fusion.get_current_comp()

    attrs = {
        "COMPN_GlobalStart": start,
        "COMPN_GlobalEnd": end
    }

    if set_render_range:
        attrs.update({
            "COMPN_RenderStart": start,
            "COMPN_RenderEnd": end
        })

    with avalon.fusion.comp_lock_and_undo_chunk(comp):
        comp.SetAttrs(attrs)


def get_next_version_folder(folder):
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


def create_new_filepath(session):

    project = session["AVALON_PROJECT"]
    asset = session["AVALON_ASSET"]

    # Save updated slap comp
    template = self._project["config"]["template"]["work"]
    template_work = pipeline._format_work_template(template, session)

    walk_to_dir = os.path.join(template_work, "scenes", "slapcomp")
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


def update_savers(comp, session):
    """Update all savers of the current comp to ensure the output is correct

    Args:
        comp (object): current comp instance
        session (dict): the current Avalon session

    Returns:
         None
    """

    template = self._project["config"]["template"]["work"]
    template_work = pipeline._format_work_template(template, session)

    render_dir = os.path.join(os.path.normpath(template_work), "renders")
    version_folder = get_next_version_folder(render_dir)
    renders_version = os.path.join(render_dir, version_folder)

    comp.Print("New renders to: %s\n" % render_dir)

    with avalon.fusion.comp_lock_and_undo_chunk(comp):
        savers = comp.GetToolList(False, "Saver").values()
        for saver in savers:
            filepath = saver.GetAttrs("TOOLST_Clip_Name")[1.0]
            filename = os.path.basename(filepath)
            new_path = os.path.join(renders_version, filename)
            saver["Clip"] = new_path


def switch(asset_name):
    """Switch the current containers of the comp to the other asset (shot)

    Args:
        asset_name (str): name of the asset (shot)

    Returns:
        comp (PyObject): the comp instance

    """

    assert asset_name, "Function requires asset name"

    host = api.registered_host()
    assert host, "Host must be installed"

    # Get current project
    self._project = io.find_one({"type": "project",
                                 "name": api.Session["AVALON_PROJECT"]})

    # Assert asset name exists
    # It is better to do this here then to wait till switch_shot does it
    asset = io.find_one({"type": "asset", "name": asset_name})
    assert asset, "Could not find '%s' in the database" % asset_name

    # Use the current open comp
    current_comp = avalon.fusion.get_current_comp()
    assert current_comp is not None, "Could not find current comp"

    containers = list(host.ls())
    assert containers, "Nothing to update"

    representations = []
    for container in containers:
        try:
            representation = colorbleed.switch_item(container,
                                                    asset_name=asset_name)
            representations.append(representation)
            log.debug(str(representation["_id"]) + "\n")
        except Exception as e:
            log.debug("Error in switching! %s\n" % e.message)

    log.info("Switched %i Loaders of the %i\n" % (len(representations),
                                                  len(containers)))
    # Updating frame range
    log.debug("\nUpdating frame range ..")
    version_ids = [r["parent"] for r in representations]
    versions = io.find({"type": "version", "_id": {"$in": version_ids}})
    versions = list(versions)

    start = min(v["data"]["startFrame"] for v in versions)
    end = max(v["data"]["endFrame"] for v in versions)

    update_frame_range(start, end, comp=current_comp)

    # Build the session to switch to
    switch_to_session = api.Session.copy()
    switch_to_session["AVALON_ASSET"] = asset['name']

    # Update session and environment
    api.Session.update(switch_to_session)
    os.environ.update(switch_to_session)

    self._project = None

    return current_comp
