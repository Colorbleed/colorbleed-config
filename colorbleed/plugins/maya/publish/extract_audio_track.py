import os
import subprocess
import contextlib
import json

import avalon.maya
from avalon.vendor import clique

import pyblish.api
import colorbleed.api

from maya import cmds, mel
# todo: replace with ffmpeg-python so it's public
import capture_gui_cb.ffmpeg as cb_ffmpeg


class ExtractAudioTrack(colorbleed.api.Extractor):
    """Extract audio track for Review.

    This will get merged in for the review quicktime if there is any audio.

    """

    label = "Audio Track"
    hosts = ["maya"]
    families = ["colorbleed.review"]
    order = pyblish.api.ExtractorOrder - 0.4

    def process(self, instance):

        audio = instance.data.get("audio", [])
        if not audio:
            self.log.info("No audio found...")
            return

        # Collect the audio files with their own offsets and generate
        # one flat audio track that we can merge into the resulting file.
        self.log.info("Creating audio track...")

        # Get time range
        start = instance.data["startFrame"]
        end = instance.data["endFrame"]
        handles = instance.data.get("handles", 0)
        if handles:
            start -= handles
            end += handles

        args = ["ffmpeg"]

        for node in instance.data["audio"]:

            audio_input_filename = cmds.getAttr(node + ".filename")
            fps = mel.eval('currentTimeUnitToFPS()')
            offset = cmds.getAttr(node + ".offset")

            offset_frames = start - offset
            offset_seconds = offset_frames / fps

            duration = (end - start) / fps

            # Offset sound clip
            if offset_seconds > 0:
                # Forward offset
                args.append("-ss")
            else:
                # Reverse offset
                args.append("-itsoffset")

            args.append(str(abs(offset_seconds)))

            args.extend(["-i", audio_input_filename])

            # Set duration for clip
            args.extend(["-t", str(duration)])

        # Need to merge audio if there are more than 1 input.
        if len(instance.data["audio"]) > 1:
            args.extend(["-filter_complex", "amerge", "-ac", "2"])

        # See: https://stackoverflow.com/a/37298513/1838864
        args.append("-vn")              # Force no video
        args.extend(["-ar", "44100"])   # Audio rate
        args.extend(["-ac", "2"])       # Audio channel count
        args.extend(["-b:a", "192k"])   # Audio bitrate

        staging = self.staging_dir(instance)
        audio_file = os.path.join(staging, "audio_track.mp3")
        args.append(audio_file)

        # Log the full command for debugging
        self.log.debug(" ".join(args))

        # Process audio
        # Can't use subprocess.check_output, cause Houdini doesn't like it.
        CREATE_NO_WINDOW = 0x08000000
        p = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW,
            cwd=os.path.dirname(args[-1])
        )

        output = p.communicate()[0]

        if p.returncode != 0:
            raise ValueError(output)

        instance.data["review_audio_file"] = audio_file
