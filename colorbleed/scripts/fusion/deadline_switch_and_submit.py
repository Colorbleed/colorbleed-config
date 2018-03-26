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
from avalon import api
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


def submit(current_comp):
    """Set rendermode to deadline and publish / submit comp"""

    # Set comp render mode to deadline
    current_comp.SetData("colorbleed.rendermode", "deadline")

    error_format = "Failed {plugin.__name__}: {error} -- {error.traceback}"

    # Publish
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
        raise RuntimeError

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
        result = True if not deadline else submit(current_comp)
    except:
        pipeline.set_current_comp(None)
        proc.terminate()  # Ensure process closes when failing
        raise RuntimeError(traceback.format_exc())  # detailed traceback

    print("Success:", result)
    print("Closing all running process ..")
    pipeline.set_current_comp(None)
    proc.terminate()


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
