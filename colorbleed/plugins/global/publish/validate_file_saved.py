import pyblish.api


class OpenWorkfilesAction(pyblish.api.Action):
    """Open Avalon Work Files tool."""
    label = "Open Work Files.."
    on = "failed"  # This action is only available on a failed plug-in
    icon = "floppy-o"  # Icon from Awesome Icon

    def process(self, context, plugin):

        from avalon.tools import workfiles
        workfiles.show()


class ValidateCurrentSaveFile(pyblish.api.ContextPlugin):
    """File must be saved before publishing"""

    label = "Validate File Saved"
    order = pyblish.api.ValidatorOrder - 0.1
    hosts = ["maya", "houdini"]
    actions = [OpenWorkfilesAction]

    def process(self, context):

        current_file = context.data["currentFile"]
        if not current_file:
            raise RuntimeError("File not saved")
