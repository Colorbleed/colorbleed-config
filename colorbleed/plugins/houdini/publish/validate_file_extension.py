import os
import pyblish.api

from colorbleed.houdini import lib


class ValidateFileExtension(pyblish.api.InstancePlugin):
    """Validate the output file extension fits the output family.

    File extensions:
        - Pointcache must be .abc
        - Camera must be .abc
        - VDB must be .vdb

    """

    order = pyblish.api.ValidatorOrder
    families = ["colorbleed.pointcache",
                "colorbleed.camera",
                "colorbleed.vdbcache"]
    hosts = ["houdini"]
    label = "Output File Extension"

    family_extensions = {
        "colorbleed.pointcache": ".abc",
        "colorbleed.camera": ".abc",
        "colorbleed.vdbcache": ".vdb"
    }

    def process(self, instance):

        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("ROP node has incorrect "
                               "file extension: %s" % invalid)

    @classmethod
    def get_invalid(cls, instance):

        import hou

        # Get ROP node from instance
        node = instance[0]

        # Create lookup for current family in instance
        families = instance.data.get("families", list())
        family = instance.data.get("family", None)
        if family:
            families.append(family)
        families = set(families)

        # Perform extension check
        output = lib.get_output_parameter(node).eval()
        _, output_extension = os.path.splitext(output)

        for family in families:
            extension = cls.family_extensions.get(family, None)
            if extension is None:
                raise RuntimeError("Unsupported family: %s" % family)

            if output_extension != extension:
                return [node.path()]
