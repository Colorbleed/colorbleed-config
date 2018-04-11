import re
import os
import json
import subprocess

import pyblish.api

from colorbleed.action import get_errored_plugins_from_data


def _get_script_dir():
    """Get path to the image sequence script"""
    try:
        import colorbleed
        config_dir = os.path.dirname(colorbleed.__file__)
        script_dir = os.path.join(config_dir, "scripts")
    except ImportError:
        raise RuntimeError("This is a bug")

    assert os.path.isdir(script_dir), "Config is incomplete"
    script_dir = script_dir.replace(os.sep, "/")

    return script_dir


class PublishImageSequence(pyblish.api.InstancePlugin):
    """Publish the generated local image sequences."""

    order = pyblish.api.IntegratorOrder
    label = "Publish Rendered Image Sequence(s)"
    hosts = ["fusion"]
    families = ["colorbleed.saver.renderlocal"]

    def process(self, instance):

        # Skip this plug-in if the ExtractImageSequence failed
        errored_plugins = get_errored_plugins_from_data(instance.context)
        if any(plugin.__name__ == "FusionRenderLocal" for plugin in
               errored_plugins):
            raise RuntimeError("Fusion local render failed, "
                               "publishing images skipped.")

        subset = instance.data["subset"]
        ext = instance.data["ext"]

        # Regex to match resulting renders
        regex = "^{subset}.*[0-9]+{ext}+$".format(subset=re.escape(subset),
                                                  ext=re.escape(ext))

        # The instance has most of the information already stored
        metadata = {
            "regex": regex,
            "startFrame": instance.context.data["startFrame"],
            "endFrame": instance.context.data["endFrame"],
            "families": ["colorbleed.imagesequence"],
        }

        # Write metadata and store the path in the instance
        output_directory = instance.data["outputDir"]
        path = os.path.join(output_directory,
                            "{}_metadata.json".format(subset))
        with open(path, "w") as f:
            json.dump(metadata, f)

        assert os.path.isfile(path), ("Stored path is not a file for %s"
                                      % instance.data["name"])

        # Suppress any subprocess console
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

        # Get script
        script_dir = _get_script_dir()
        script = os.path.join(script_dir, "publish_imagesequence.py")
        assert os.path.isfile(script), ("Config incomplete, missing "
                                        "`script/publish_imagesequence.py`")

        process = subprocess.Popen(["python", script,
                                    "--paths", path],
                                   bufsize=1,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,
                                   startupinfo=startupinfo)

        while True:
            output = process.stdout.readline()
            # Break when there is no output or a return code has been given
            if output == '' and process.poll() is not None:
                process.stdout.close()
                break
            if output:
                line = output.strip()
                if line.startswith("ERROR"):
                    self.log.error(line)
                else:
                    self.log.info(line)

        if process.returncode != 0:
            raise RuntimeError("Process quit with non-zero "
                               "return code: {}".format(process.returncode))
