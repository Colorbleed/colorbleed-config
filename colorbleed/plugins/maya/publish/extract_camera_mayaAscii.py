import os

from maya import cmds

import avalon.maya
import colorbleed.api
from colorbleed.lib import grouper
from colorbleed.maya import lib


def massage_ma_file(path):
    """Clean up .ma file for backwards compatibility.

    Massage the .ma of baked camera to stay
    backwards compatible with older versions
    of Fusion (6.4)

    """
    # Get open file's lines
    f = open(path, "r+")
    lines = f.readlines()
    f.seek(0)  # reset to start of file

    # Rewrite the file
    for line in lines:
        # Skip all 'rename -uid' lines
        stripped = line.strip()
        if stripped.startswith("rename -uid "):
            continue

        f.write(line)

    f.truncate()  # remove remainder
    f.close()


def unlock(plug):
    """Unlocks attribute and disconnects inputs for a plug.

    This will also recursively unlock the attribute
    upwards to any parent attributes for compound
    attributes, to ensure it's fully unlocked and free
    to change the value.

    """
    node, attr = plug.rsplit(".", 1)

    # Unlock attribute
    cmds.setAttr(plug, lock=False)

    # Also unlock any parent attribute (if compound)
    parents = cmds.attributeQuery(attr, node=node, listParent=True)
    if parents:
        for parent in parents:
            unlock("{0}.{1}".format(node, parent))

    # Break incoming connections
    connections = cmds.listConnections(plug,
                                       source=True,
                                       destination=False,
                                       plugs=True,
                                       connections=True)
    if connections:
        for destination, source in grouper(connections, 2):
            cmds.disconnectAttr(source, destination)


class ExtractCameraMayaAscii(colorbleed.api.Extractor):
    """Extract a Camera as Maya Ascii.

    This will create a duplicate of the camera that will be baked *with*
    substeps and handles for the required frames. This temporary duplicate
    will be published.

    The cameras gets baked to world space by default. Only when the instance's
    `bakeToWorldSpace` is set to False it will include its full hierarchy.

    Note:
        The extracted Maya ascii file gets "massaged" removing the uuid values
        so they are valid for older versions of Fusion (e.g. 6.4)

    """

    label = "Camera (Maya Ascii)"
    hosts = ["maya"]
    families = ["colorbleed.camera"]

    def process(self, instance):

        # get settings
        framerange = [instance.data.get("startFrame", 1),
                      instance.data.get("endFrame", 1)]
        handles = instance.data.get("handles", 0)
        step = instance.data.get("step", 1.0)
        bake_to_worldspace = instance.data("bakeToWorldSpace", True)

        # TODO: Implement a bake to non-world space
        # Currently it will always bake the resulting camera to world-space
        # and it does not allow to include the parent hierarchy, even though
        # with `bakeToWorldSpace` set to False it should include its
        # hierarchy to be correct with the family implementation.
        if not bake_to_worldspace:
            self.log.warning("Camera (Maya Ascii) export only supports world"
                             "space baked camera extractions. The disabled "
                             "bake to world space is ignored...")

        # get cameras
        members = instance.data['setMembers']
        cameras = cmds.ls(members, leaf=True, long=True,
                          dag=True, type="camera")

        range_with_handles = [framerange[0] - handles,
                              framerange[1] + handles]

        # validate required settings
        assert len(cameras) == 1, "Not a single camera found in extraction"
        assert isinstance(step, float), "Step must be a float value"
        camera = cameras[0]
        transform = cmds.listRelatives(camera, parent=True, fullPath=True)

        # Define extract output file path
        dir_path = self.staging_dir(instance)
        filename = "{0}.ma".format(instance.name)
        path = os.path.join(dir_path, filename)

        # Perform extraction
        self.log.info("Performing camera bakes for: {0}".format(transform))
        with avalon.maya.maintained_selection():
            with lib.evaluation("off"):
                with avalon.maya.suspended_refresh():
                    baked = lib.bake_to_world_space(
                        transform,
                        frame_range=range_with_handles,
                        step=step
                    )
                    try:
                        baked_shapes = cmds.ls(baked,
                                                           type="camera",
                                                           dag=True,
                                                           long=True)

                        # Fix PLN-178: Don't allow background color to be non-black
                        for cam in baked_shapes:
                            attrs = {"backgroundColorR": 0.0,
                                     "backgroundColorG": 0.0,
                                     "backgroundColorB": 0.0,
                                     "overscan": 1.0}
                            for attr, value in attrs.items():
                                plug = "{0}.{1}".format(cam, attr)
                                unlock(plug)
                                cmds.setAttr(plug, value)

                        self.log.info("Performing extraction..")
                        cmds.select(baked_shapes, noExpand=True)
                        cmds.file(path,
                                  force=True,
                                  typ="mayaAscii",
                                  exportSelected=True,
                                  preserveReferences=False,
                                  constructionHistory=False,
                                  channels=True,  # allow animation
                                  constraints=False,
                                  shader=False,
                                  expressions=False)
                    finally:
                        # Use try..finally so that baked camera is always
                        # deleted, even when a command errors above.
                        # Delete the baked hierarchy
                        cmds.delete(baked)

                    massage_ma_file(path)

        if "files" not in instance.data:
            instance.data["files"] = list()

        instance.data["files"].append(filename)

        self.log.info("Extracted instance '{0}' to: {1}".format(
            instance.name, path))
