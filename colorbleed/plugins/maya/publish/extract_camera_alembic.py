import os

from maya import cmds

import avalon.maya
import colorbleed.api

import colorbleed.maya.lib as lib


class ExtractCameraAlembic(colorbleed.api.Extractor):
    """Extract a Camera as Alembic.

    The cameras gets baked to world space by default. Only when the instance's
    `bakeToWorldSpace` is set to False it will include its full hierarchy.

    """

    label = "Camera (Alembic)"
    hosts = ["maya"]
    families = ["colorbleed.camera"]

    def process(self, instance):

        # get settings
        framerange = [instance.data.get("startFrame", 1),
                      instance.data.get("endFrame", 1)]
        handles = instance.data.get("handles", 0)
        step = instance.data.get("step", 1.0)
        bake_to_worldspace = instance.data("bakeToWorldSpace", True)
        euler_filter = instance.data("eulerFilter", False)

        # get cameras
        members = instance.data['setMembers']
        cameras = cmds.ls(members, leaf=True, long=True,
                          dag=True, type="camera")

        # validate required settings
        assert len(cameras) == 1, "Not a single camera found in extraction"
        assert isinstance(step, float), "Step must be a float value"
        camera = cameras[0]

        # Define extract output file path
        dir_path = self.staging_dir(instance)
        filename = "{0}.abc".format(instance.name)
        path = os.path.join(dir_path, filename)

        # Perform alembic extraction
        with avalon.maya.maintained_selection():
            cmds.select(camera, replace=True, noExpand=True)

            # Enforce forward slashes for AbcExport because we're
            # embedding it into a job string
            path = path.replace("\\", "/")

            job_str = ' -selection -dataFormat "ogawa" '
            job_str += ' -attrPrefix cb'
            job_str += ' -frameRange {0} {1} '.format(framerange[0] - handles,
                                                      framerange[1] + handles)
            job_str += ' -step {0} '.format(step)

            if bake_to_worldspace:
                transform = cmds.listRelatives(camera,
                                               parent=True,
                                               fullPath=True)[0]
                job_str += ' -worldSpace -root {0}'.format(transform)

            if euler_filter:
                job_str += ' -eulerFilter'

            job_str += ' -file "{0}"'.format(path)

            with lib.evaluation("off"):
                with avalon.maya.suspended_refresh():
                    cmds.AbcExport(j=job_str, verbose=False)

        if "files" not in instance.data:
            instance.data["files"] = list()

        instance.data["files"].append(filename)

        self.log.info("Extracted instance '{0}' to: {1}".format(
            instance.name, path))
