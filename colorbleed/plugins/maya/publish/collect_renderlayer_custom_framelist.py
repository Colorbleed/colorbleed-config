import os
import re
import subprocess

import pyblish.api

from maya import cmds
from maya import mel

from colorbleed.maya import lib


CREATE_NO_WINDOW = 0x08000000


def deadline_parse_framelist(framelist):
    result = deadline_command("ParseFrameList", framelist)
    frames = []
    for entry in result.split(","):

        # Clean any new-lines or spaces
        entry = entry.strip()

        # Match a single positive or negative number or a sequence
        # defined as start-end which also supports negative ranges
        # like -10--5 (-10 through to -5)
        pattern = r"^(?P<start>-?[0-9]+)(?:(?:-)(?P<end>-?[0-9]+))?$"
        match = re.match(pattern, entry)

        start = int(match.group("start"))
        end = match.group("end")
        if end is None:
            # Single frame (start)
            frames.append(start)
        else:
            # Range of frames (start-end)
            end = int(end)
            frames.extend(range(start, end + 1))

    return frames


def deadline_command(*args):
    # Find Deadline
    path = os.environ.get("DEADLINE_PATH", None)
    assert path is not None, "Variable 'DEADLINE_PATH' must be set"

    executable = os.path.join(path, "deadlinecommand")
    if os.name == "nt":
        executable += ".exe"
    assert os.path.exists(
        executable), "Deadline executable not found at %s" % executable
    query = [executable] + list(args)

    process = subprocess.Popen(query, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               universal_newlines=True,
                               creationflags=CREATE_NO_WINDOW)
    out, err = process.communicate()

    return out


class CollectRenderlayerCustomFramelist(pyblish.api.InstancePlugin):
    """Collect the renderlayer's frame list set in renderglobalsDefault

    This will collec the Custom Framelist value from the renderglobalsDefault
    node for the specific renderlayer (as it could have a renderlayer override)

    """

    order = pyblish.api.CollectorOrder + 0.4999
    label = "Render Framelist"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer"]

    def process(self, instance):

        # Remove any collected data that other generic collectors have
        # collected thus far.
        instance.data.pop("useCustomFrameList", None)
        instance.data.pop("frameList", None)

        node = "renderglobalsDefault"
        assert cmds.objExists(node), "renderglobalsDefault does not exist"

        # Get the renderlayer for this instance
        layer = instance.data["setMembers"]

        # Backwards compatibility for older instances
        if not cmds.attributeQuery("userCustomFrameList",
                                   node=node,
                                   exists=True):
            self.log.info("Old renderglobalsDefault instance detected without "
                          "`useCustomFrameList` attribute. Ignoring..")
            return

        # Get settings from renderGlobalsDefault node in that layer
        use_frame_list = lib.get_attr_in_layer(node + ".useCustomFrameList",
                                               layer=layer)
        instance.data["useCustomFrameList"] = use_frame_list
        if not use_frame_list:
            return

        frame_list = lib.get_attr_in_layer(node + ".frameList",
                                           layer=layer).strip()

        # Parse the actual frames with Deadline Command to ensure it's a
        # valid framelist string.
        frames = deadline_parse_framelist(frame_list)
        frames = sorted(frames)

        self.log.info("Collected custom framelist: %s" % frame_list)

        instance.data["frameList"] = frame_list
        instance.data["frames"] = frames

        # Ensure start + end frame comes from the start/end
        # of the explicit custom frame list formatting so the
        # published data makes sense.
        start = frames[0]
        end = frames[-1]
        self.log.info("Setting start and end frame: %s - %s" % (start, end))
        instance.data["startFrame"] = start
        instance.data["endFrame"] = end

        # todo(roy): move this update label code elsewhere
        # Update instance label for correct frame ranges
        label = instance.data["label"]
        base = label.rsplit("  [", 1)[0]    # split off frame range
        label = "{0}  [{1}]".format(base, frame_list)
        instance.data["label"] = label
