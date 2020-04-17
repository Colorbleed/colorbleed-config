from avalon import api


class ShowInUsdview(api.Loader):
    """Open USD file in usdview"""

    families = ["colorbleed.usd"]
    label = "Show in usdview"
    representations = ["usd", "usda", "usdlc", "usdnc"]
    order = 10

    icon = "code-fork"
    color = "white"

    def load(self, context, name=None, namespace=None, data=None):

        import os
        import subprocess

        import avalon.lib as lib

        usdview = lib.which("usdview")

        filepath = os.path.normpath(self.fname)
        filepath = filepath.replace("\\", "/")

        if not os.path.exists(filepath):
            self.log.error("File does not exist: %s" % filepath)
            return

        self.log.info("Start houdini variant of usdview...")

        # For now avoid some pipeline environment variables that initialize
        # Avalon in Houdini as it is redundant for usdview and slows boot time
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("HOUDINI_SCRIPT_PATH", None)
        env.pop("HOUDINI_MENU_PATH", None)

        # Force string to avoid unicode issues
        env = {str(key): str(value) for key, value in env.items()}

        subprocess.Popen([usdview, filepath, "--renderer", "GL"],
                         env=env)
