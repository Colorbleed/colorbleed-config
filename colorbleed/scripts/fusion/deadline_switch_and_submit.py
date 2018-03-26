"""
This holds the logic to open a comp, switch the assets (shot), save it with
the correct naming. Optionally the new comp can be submitted to Deadline to
render and publish the output

This module is for a standalone approach for Fusion similar to Maya.
Note that this will require FusionConsoleNode.exe and the BlackmagicFusion
module.

Deadline runs a python process, lets call it P

P will start the FusionConsoleNode in a new SUBPROCESS
This SUBPROCESS will need to have the same environment as P to ensure it can
use AVALON

    P --> SUBPROCESS (FusionConsoleNode.EXE /listen)

From the SUBPROCESS comes a Fusion Console Node which will be used as the Fusion
instance to work in. In order to get the correct Fusion instance we use a
ScriptServer to get all Fusion programs which are running.
This is done by comparing the process ids with the subprocess.pid.

    See `get_fusion_instance` function for more details

In `avalon.fusion.pipeline` we have create a work around to get the fusion
instance. This is done through

    getattr(sys.module["__main__"], "fusion", None)

Because we do this we can also allow to set correct fusion module, this is done
by using the setattr. This will ensure that all other functions which are run
within `process()` can find `fusion`.

"""

import subprocess
import traceback
import logging
import time
import sys
import os

log = logging.getLogger(__name__)

# This script only works with Python 2.7 and 3.6
version = "{0}{1}".format(*sys.version_info)  # {major}{minor}
assert version in ["27", "36"], "Script only works in Python 2.7 or 3.6"
key = "FUSION_PYTHON{0}_HOME".format(version)

# Importing BlackmagicFusion package in standalone Python interpreter
# crashes when not installed on default location but runs from, e.g. a
# network share. Forcing Fusion's Python home magically fixes it.
print("Setting %s to Python executable directory.." % key)
os.environ[key] = os.path.dirname(sys.executable)

# TODO: define these paths somewhere else
FUSCRIPT_EXE = r"C:/Program Files/Blackmagic Design/Fusion9/FuScript.exe"
FUSION_CONSOLE_EXE = r"C:/Program Files/Blackmagic Design/Fusion Render Node 9/FusionConsoleNode.exe"

# Pipeline and config imports
import avalon.fusion
from avalon import io, api, pipeline

import colorbleed.lib as cblib
import colorbleed.fusion.lib as fusionlib

# Application related imports
import BlackmagicFusion as bmf


def start_server():
    bmf.startserver()
    return get_server()


def get_server(tries=10, timeout=0.5):

    count = 0
    srv = None

    while not srv:
        count += 1
        print("Connecting to ScriptServer (try: %s)" % count)
        srv = bmf.scriptapp("", "localhost", timeout)  # Runs script server
        if count > tries:
            break

    return srv


def get_fusion_instance(pid, srv, timeout=10):
    """Get the fusion instance which has been launched"""

    count = 0
    host = None
    while not host:
        if count > timeout:
            break
        fusion_hosts = srv.GetHostList().values()
        host = next((i for i in fusion_hosts if int(i["ProcessID"]) == pid),
                    None)
        if not host:
            print("Find Fusion host... (%ss)" % count)
            time.sleep(0.5)
            count += 0.5

    assert host, "Fusion not found with pid: %s" % pid

    return bmf.scriptapp(host["Name"], "localhost", 2, host["UUID"])


def create_new_filepath(session):
    """
    Create a new fil epath based on the session and the project's template

    Args:
        session (dict): the Avalon session

    Returns:
        file path (str)

    """

    # Save updated slap comp
    project = io.find_one({"type": "project",
                           "name": session["AVALON_PROJECT"]})

    template = project["config"]["template"]["work"]
    template_work = pipeline._format_work_template(template, session)

    walk_to_dir = os.path.join(template_work, "scenes", "slapcomp")
    slapcomp_dir = os.path.abspath(walk_to_dir)

    # Ensure destination exists
    if not os.path.isdir(slapcomp_dir):
        log.warning("Folder did not exist, creating folder structure")
        os.makedirs(slapcomp_dir)

    # Compute output path
    new_filename = "{}_{}_slapcomp_v001.comp".format(session["AVALON_PROJECT"],
                                                     session["AVALON_ASSET"])
    new_filepath = os.path.join(slapcomp_dir, new_filename)

    # Create new unqiue filepath
    if os.path.exists(new_filepath):
        new_filepath = cblib.version_up(new_filepath)

    return new_filepath


def submit(current_comp):
    """Set rendermode to deadline and publish / submit comp"""

    # Set comp render mode to deadline
    current_comp.SetData("colorbleed.rendermode", "deadline")

    error_format = "Failed {plugin.__name__}: {error} -- {error.traceback}"

    # Publish
    context = api.publish()
    if not context:
        raise RuntimeError("Nothing collected for publish")

    # Collect errors, {plugin name: error}, if any
    error_results = [r for r in context.data["results"] if r["error"]]
    if error_results:
        for result in error_results:
            log.error(error_format.format(**result))
        raise RuntimeError("Errors occured")

    return True


def process(file_path, asset_name, deadline=False):
    """Run switch in a Fusion Console Node (cmd)

    Open the comp (file_path) and switch to the asset (asset_name) and when
    deadline is enabled it will submit the switched comp to Deadline to render
    and publish the output.

    Args:
        file_path (str): File path of the comp to use
        asset_name (str): Name of the asset (shot) to switch
        deadline (bool, optional): If set True the new composition file will be
                                   used to render
    Returns:
        None

    """

    # Start a fusion console node in "listen" mode
    proc = subprocess.Popen([FUSION_CONSOLE_EXE, "/listen"])

    srv = get_server()
    if not srv:
        log.info("No server found, starting server ..")
        srv = start_server()

    # Force fusion into main magical module so that host.ls() works
    fusion = get_fusion_instance(proc.pid, srv)
    assert fusion
    log.info("Connected to: %s" % fusion)
    setattr(sys.modules["__main__"], "fusion", fusion)

    api.install(avalon.fusion)
    from avalon.fusion import pipeline

    # This does not set
    loaded_comp = fusion.LoadComp(file_path)
    if not loaded_comp:
        raise RuntimeError("Comp could not be loaded. File '%s'" % file_path)

    pipeline.set_current_comp(loaded_comp)
    current_comp = pipeline.get_current_comp()

    assert loaded_comp == current_comp, "Could not find the correct comp"
    print("Loaded comp name: %s" % current_comp.GetAttrs("COMPS_FileName"))

    try:
        # Execute script in comp
        fusionlib.switch(asset_name=asset_name)
        new_file_path = create_new_filepath(api.Session)
        current_comp.Save(new_file_path)
        if deadline:
            submit(current_comp)
    except Exception:
        print(traceback.format_exc())  # ensure detailed traceback
        raise
    finally:
        pipeline.set_current_comp(None)
        print("Closing running process ..")
        proc.terminate()  # Ensure process closes when failing


# Usability for deadline job submission
if __name__ == '__main__':

    import argparse

    parser = argparse.ArgumentParser(description="Switch to a shot within an"
                                                 "existing comp file")

    parser.add_argument("--file_path",
                        type=str,
                        default=True,
                        help="File path of the comp to use")

    parser.add_argument("--asset_name",
                        type=str,
                        default=True,
                        help="Name of the asset (shot) to switch")

    parser.add_argument("--render",
                        default=False,
                        help="If set True the new composition file will be used"
                             "to render")

    args = parser.parse_args()

    process(file_path=args.file_path,
            asset_name=args.asset_name,
            deadline=args.render)
