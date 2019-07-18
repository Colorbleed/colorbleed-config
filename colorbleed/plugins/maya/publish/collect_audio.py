from maya import cmds, mel

import pyblish.api


def get_audio_settings():
    """Return audio settings from time slider.

    This function is slightly more involved because it can also get the time
    slider settings for audio in maya standalone mode without interface by
    reading the scene's `uiConfigurationScriptNode`

    """

    # Get settings from the time slider
    playback_slider = mel.eval('$gPlayBackSlider=$gPlayBackSlider')
    if playback_slider:
        return {
            "sound": cmds.timeControl(playback_slider,
                                      query=True,
                                      sound=True),
            "displaySound": cmds.timeControl(playback_slider,
                                             query=True,
                                             displaySound=True)
        }

    # If the time slider does not exist then we're likely in maya batch mode.
    assert cmds.about(batch=True), "Must be in Maya batch mode"

    # Then we'll revert to reading the uiConfigurationScriptNode to get the
    # setting that was saved along with the file and that would initialize
    # the UI.
    ui_node = cmds.ls("uiConfigurationScriptNode", type="script")
    if ui_node:
        ui_script = cmds.getAttr("uiConfigurationScriptNode.before")

        # Reverse the lines, because the command is usually at the end.
        # Plus that way we ensure we have the last call to it if it
        # miraculously ends up more than once inside the script node.
        for line in reversed(ui_script.split("\n")):
            match = re.search("timeControl(.+)\$gPlayBackSlider;", line)
            if match:
                flags = match.group(1)
                # Get all arguments with values
                flags_match = re.findall("-(\w+) (\w+) ", flags)
                kwargs = {key: value for key, value in flags_match}

                return {
                    "sound": kwargs.get("sound", None),
                    "displaySound": int(kwargs.get("displaySound", 1))
                }

    # If even that failed, just return some defaults that would use all
    # sound nodes in the scene
    return {"sound": None, "displaySound": True}


class CollectReviewAudio(pyblish.api.InstancePlugin):
    """Collect the audio files with offsets from the timeline."""

    order = pyblish.api.CollectorOrder + 0.4
    label = "Timeline Audio"
    families = ["colorbleed.review"]
    hosts = ['maya']

    def process(self, instance):

        if not instance.data.get("includeAudio", True):
            # Skip when "includeAudio" is False on instance.
            return

        start_frame = instance.data["startFrame"]
        end_frame = instance.data["endFrame"]

        # Collect audio
        settings = get_audio_settings()
        audio_name = settings.get("sound")  # explicit audio file
        display_sounds = settings.get("displaySounds", True)

        audio = []
        if audio_name:
            audio.append(audio_name)

        if not audio_name and display_sounds:

            for node in cmds.ls(type="audio"):
                # Check if frame range and audio range intersects,
                # for whether to include this audio node or not.

                offset = cmds.getAttr(node + ".offset")
                duration = cmds.getAttr(node + ".duration")

                start_audio = offset
                end_audio = offset + duration

                # They overlap whenever it starts before the end frame
                # and ends somewhere after the start frame.
                if start_audio <= end_frame and end_audio >= start_frame:
                    audio.append(node)

        instance.data["audio"] = audio
