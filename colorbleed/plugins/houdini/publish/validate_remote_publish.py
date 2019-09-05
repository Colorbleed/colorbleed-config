import pyblish.api
import colorbleed.api

import hou


class ValidateRemotePublishOutNode(pyblish.api.InstancePlugin):
    """Validate the remote publish out node exists for Deadline to trigger."""

    order = colorbleed.api.ValidateContentsOrder - 0.4
    families = ["*"]
    hosts = ['houdini']
    targets = ["deadline"]
    label = 'Remote Publish ROP node'
    actions = [colorbleed.api.RepairAction]

    cmd = "import pyblish.util; pyblish.util.publish()"

    def process(self, instance):

        # todo: refactor to context plugin

        node = hou.node("/out/REMOTE_PUBLISH")
        if not node:
            raise RuntimeError("Missing REMOTE_PUBLISH node.")

        # We ensure it's a shell node and that it has the pre-render script
        # set correctly. Plus the shell script it will trigger should be
        # completely empty (doing nothing)
        assert node.type().name() == "shell", "Must be shell ROP node"
        assert node.parm("command").eval() == "", "Must have no command"
        assert not node.parm("shellexec").eval(), "Must not execute in shell"
        assert node.parm("prerender").eval() == self.cmd, (
            "REMOTE_PUBLISH node does not have correct prerender script."
        )
        assert node.parm("lprerender").eval() == "python", (
            "REMOTE_PUBLISH node prerender script type not set to 'python'"
        )

    @classmethod
    def repair(cls, instance):
        """(Re)create the node if it fails to pass validation"""

        existing = hou.node("/out/REMOTE_PUBLISH")
        if existing:
            cls.log.warning("Removing existing '/out/REMOTE_PUBLISH' node..")
            existing.destroy()

        # Create the shell node
        out = hou.node("/out")
        shell = out.createNode("shell", node_name="REMOTE_PUBLISH")
        shell.moveToGoodPosition()

        # Set the pre-render script
        shell.setParms({
            "prerender": cls.cmd,
            "lprerender": "python"  # command language
        })

        # Lock the attributes to ensure artists won't easily mess things up.
        shell.parm("prerender").lock(True)
        shell.parm("lprerender").lock(True)

        # Lock up the actual shell command
        command_parm = shell.parm("command")
        command_parm.set("")
        command_parm.lock(True)
        command_parm.hide(True)
        shellexec_parm = shell.parm("shellexec")
        shellexec_parm.set(False)
        shellexec_parm.lock(True)
        shellexec_parm.hide(True)

        # Tweak the node's template so it's a lot clearer to the artist.
        # todo: Hide the Shell tab itself (python code below still shows tab)
        # template = node.parmTemplateGroup()
        # template.hideFolder("Shell", True)
        # node.setParmTemplateGroup(template)
