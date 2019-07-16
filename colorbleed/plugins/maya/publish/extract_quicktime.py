import os
import subprocess
import contextlib
import json

import avalon.maya
from avalon.vendor import clique

import colorbleed.api

from maya import cmds, mel
import capture_gui.lib

# todo: replace with ffmpeg-python so it's public
import capture_gui_cb.ffmpeg as cb_ffmpeg


def _get_focal_length(cam, start, end):
    plug = "{0}.focalLength".format(cam)
    if not cmds.listConnections(plug, destination=False, source=True):
        # static
        return cmds.getAttr(plug)
    else:
        # dynamic
        return [cmds.getAttr(plug, time=t) for t in range(int(start),
                                                          int(end))]


class ExtractQuicktime(colorbleed.api.Extractor):
    """Extract Quicktime from viewport capture.

    Takes review camera and creates review Quicktime video based on viewport
    capture.

    """

    label = "Quicktime"
    hosts = ["maya"]
    families = ["colorbleed.review"]

    def process(self, instance):
        self.log.info("Extracting capture..")

        # Get scene FPS
        fps = mel.eval('currentTimeUnitToFPS()')

        # Get time range
        start = instance.data["startFrame"]
        end = instance.data["endFrame"]
        handles = instance.data.get("handles", 0)
        if handles:
            start -= handles
            end += handles

        # Get camera
        members = instance.data['setMembers']
        cameras = cmds.ls(members, leaf=True, shapes=True, long=True,
                          dag=True, type="camera")
        assert len(cameras) == 1, "Not a single camera found in extraction"
        camera = cameras[0]

        # Get settings
        include_alpha = instance.data.get("include_alpha", False)

        # Define capture options
        # Override some preset defaults
        preset = {}
        preset['camera'] = camera
        preset['start_frame'] = start
        preset['end_frame'] = end
        preset['show_ornaments'] = False    # Don't draw any Maya HUD

        # Extract to image sequence, then we convert afterwards with ffmpeg
        preset['off_screen'] = True
        preset['format'] = "image"
        preset['quality'] = 95

        if include_alpha:
            preset["compression"] = "png"
        else:
            preset['compression'] = "jpg"

        preset['camera_options'] = {
            "displayGateMask": False,
            "displayResolution": False,
            "displayFilmGate": False,
            "displayFieldChart": False,
            "displaySafeAction": False,
            "displaySafeTitle": False,
            "displayFilmPivot": False,
            "displayFilmOrigin": False,
            "overscan": 1.0,
            "depthOfField": cmds.getAttr("{0}.depthOfField".format(camera)),
        }

        self.log.info('using viewport preset: {}'.format(preset))
        # todo: state of ambient occlusion, lighting, double sided, etc?

        stagingdir = self.staging_dir(instance)
        filename = "{0}".format(instance.name)
        path = os.path.join(stagingdir, filename)
        self.log.info("Outputting images to %s" % path)

        preset['filename'] = path

        # It always writes to a new staging dir so we should never be
        # overwriting anything
        preset['overwrite'] = False

        with maintained_time():
            playblast = capture_gui.lib.capture_scene(preset)

        self.log.info("file list  {}".format(playblast))
        assert playblast, "Playblast likely interrupted.."

        # Collect playblasted frames
        collected_frames = os.listdir(stagingdir)
        # todo: support negative frames as input
        collections, remainder = clique.assemble(collected_frames)
        assert not remainder, (
            "Remaining frames found, this is incorrect.. (or negative frames?)"
        )
        assert len(collections) == 1, (
            "Must find a single image sequence, found: %s" % (collections,)
        )

        input_path = os.path.join(
            stagingdir, collections[0].format('{head}{padding}{tail}'))
        self.log.info("input {}".format(input_path))

        movie_file = filename + ".mov"
        movie_file_burnin = filename + ".burnin" + ".mov"

        full_movie_path = os.path.join(stagingdir, movie_file)
        full_burnin_path = os.path.join(stagingdir, movie_file_burnin)

        self.log.info("output {}".format(full_movie_path))

        with avalon.maya.suspended_refresh():

            # Render ffmpeg without burnin
            self.log.info("Creating video..")
            cb_ffmpeg.render(source=input_path,
                             output=full_movie_path,
                             fps=fps,       # for image sequence FPS
                             start=start,   # for image sequence start frame
                             logo=False,
                             include_alpha=include_alpha,
                             # Hide the subprocess window
                             create_no_window=True,
                             verbose=True)

            # Render ffmpeg with burnin
            self.log.info("Creating burnin video..")
            scene = os.path.basename(instance.context.data["currentFile"])
            cb_ffmpeg.overlay_video(source=input_path,
                                    output=full_burnin_path,
                                    start=start,
                                    end=end,
                                    scene=scene,
                                    username="",
                                    focal_length=_get_focal_length(camera,
                                                                   start,
                                                                   end),
                                    fps=fps,
                                    include_alpha=include_alpha,
                                    # Hide the subprocess window
                                    create_no_window=True,
                                    verbose=True)

        if "files" not in instance.data:
            instance.data["files"] = []

        # Store both the version without burnin and with burnin
        instance.data["files"].append(movie_file)
        instance.data["files"].append(movie_file_burnin)


@contextlib.contextmanager
def maintained_time():
    ct = cmds.currentTime(query=True)
    try:
        yield
    finally:
        cmds.currentTime(ct, edit=True)
