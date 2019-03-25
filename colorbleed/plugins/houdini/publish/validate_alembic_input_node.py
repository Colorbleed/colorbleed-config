import pyblish.api
import colorbleed.api


class ValidateAlembicInputNode(pyblish.api.InstancePlugin):
    """Validate that the node connected to the output is correct

    The connected node cannot be of the following types for Alembic:
        - VDB
        - Volume

    """

    order = colorbleed.api.ValidateContentsOrder + 0.1
    families = ["colorbleed.pointcache"]
    hosts = ["houdini"]
    label = "Validate Input Node (Abc)"

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Primitive types found that are not supported"
                               "for Alembic output.")

    @classmethod
    def get_invalid(cls, instance):

        invalid_prim_types = ["VDB", "Volume"]
        node = instance.data["output_node"]

        geo = node.geometry()
        invalid = False
        for prim_type in invalid_prim_types:
            if geo.countPrimType(prim_type) > 0:
                cls.log.error("Found a primitive which is of type '%s' !"
                              % prim_type)
                invalid = True

        if invalid:
            return [instance]
