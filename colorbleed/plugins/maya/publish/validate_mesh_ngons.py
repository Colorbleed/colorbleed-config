from maya import cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.action
import colorbleed.maya.lib as lib


class ValidateMeshNGONS(pyblish.api.Validator):
    """Ensure that meshes don't have NGONs. Only allow triangles and quads.

    This is implemented due to Redshift USD being unable to render NGONs
    correctly in Houdini in LOPs/Solaris (from USD) files. Redshift will
    render the faces black.

    Also note that Multiverse 6.3.0 (and likely before) seems to export NGONs
    wrong compared to Houdini's export. This has been reported and is likely
    to get fixed in new versions.

    To debug the problem on the meshes you can use Maya's modeling
    tool: "Mesh > Cleanup..."

    """

    order = colorbleed.api.ValidateMeshOrder
    hosts = ['maya']
    families = ['usdModel']
    label = 'Mesh NGONs'
    actions = [colorbleed.maya.action.SelectInvalidAction]

    @staticmethod
    def get_invalid(instance):

        meshes = cmds.ls(instance, type='mesh', long=True)

        # Get all faces
        faces = ['{0}.f[*]'.format(node) for node in meshes]

        # Filter to n-sided polygon faces (ngons)
        invalid = lib.polyConstraint(faces,
                                     t=0x0008,  # type=face
                                     size=3)    # size=nsided

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance 'objectSet'"""

        invalid = self.get_invalid(instance)

        if invalid:
            raise ValueError("Meshes found with NGONs: {0}".format(invalid))
