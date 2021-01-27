import os
import contextlib

from maya import cmds

import avalon.maya
import colorbleed.api
import colorbleed.maya.lib as lib


@contextlib.contextmanager
def no_color_sets(nodes, enabled=True):
    """Temporarily remove mesh color sets using undo chunk"""

    if not enabled:
        # Do nothing
        yield
        return

    mesh_colors = {}
    for mesh in cmds.ls(nodes, type="mesh"):
        color_sets = cmds.polyColorSet(mesh,
                                       query=True,
                                       allColorSets=True)
        if color_sets:
            mesh_colors[mesh] = color_sets

    if not mesh_colors:
        yield
        return

    try:
        cmds.undoInfo(openChunk=True, chunkName="no_color_set (context)")
        for mesh, color_sets in mesh_colors.items():
            for color_set in color_sets:
                cmds.polyColorSet(mesh, delete=True, colorSet=color_set)
        yield
    finally:
        cmds.undoInfo(closeChunk=True)
        cmds.undo()


class ExtractModel(colorbleed.api.Extractor):
    """Extract as Model (Maya Ascii)

    Only extracts contents based on the original "setMembers" data to ensure
    publishing the least amount of required shapes. From that it only takes
    the shapes that are not intermediateObjects

    During export it sets a temporary context to perform a clean extraction.
    The context ensures:
        - Smooth preview is turned off for the geometry
        - Default shader is assigned (no materials are exported)
        - Remove display layers

    """

    label = "Model (Maya ASCII)"
    hosts = ["maya"]
    families = ["colorbleed.model"]

    def process(self, instance):

        # Define extract output file path
        stagingdir = self.staging_dir(instance)
        filename = "{0}.ma".format(instance.name)
        path = os.path.join(stagingdir, filename)

        # Perform extraction
        self.log.info("Performing extraction..")

        # Get only the shape contents we need in such a way that we avoid
        # taking along intermediateObjects
        members = instance.data("setMembers")
        members = cmds.ls(members,
                          dag=True,
                          shapes=True,
                          type=("mesh", "nurbsCurve"),
                          noIntermediate=True,
                          long=True)

        remove_color_sets = not instance.data.get("writeColorSets", False)

        with no_color_sets(members, enabled=remove_color_sets):
            with lib.no_display_layers(instance):
                with lib.displaySmoothness(members,
                                           divisionsU=0,
                                           divisionsV=0,
                                           pointsWire=4,
                                           pointsShaded=1,
                                           polygonObject=1):
                    with lib.shader(members,
                                    shadingEngine="initialShadingGroup"):
                        with avalon.maya.maintained_selection():
                            cmds.select(members, noExpand=True)
                            cmds.file(path,
                                      force=True,
                                      typ="mayaAscii",
                                      exportSelected=True,
                                      preserveReferences=False,
                                      channels=False,
                                      constraints=False,
                                      expressions=False,
                                      constructionHistory=False)

                        # Store reference for integration

        if "files" not in instance.data:
            instance.data["files"] = list()

        instance.data["files"].append(filename)

        self.log.info("Extracted instance '%s' to: %s" % (instance.name, path))
