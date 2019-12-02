import pyblish.api


class CollectOutputNodePath(pyblish.api.InstancePlugin):
    """Collect the out node's SOP/COP Path value."""

    order = pyblish.api.CollectorOrder
    families = ["colorbleed.pointcache",
                "colorbleed.camera",
                "colorbleed.vdbcache",
                "colorbleed.imagesequence",
                "colorbleed.usd"]
    hosts = ["houdini"]
    label = "Collect Output Node Path"

    def process(self, instance):

        import hou

        node = instance[0]

        # Get sop path
        node_type = node.type().name()
        if node_type == "geometry":
            path = node.parm("soppath").eval()
        elif node_type == "alembic":

            # Alembic can switch between using SOP Path or object
            if node.parm("use_sop_path").eval():
                path = node.parm("sop_path").eval()
            else:
                root = node.parm("root").eval()
                objects = node.parm("objects").eval()
                path = root + "/" + objects

        elif node_type == "comp":
            path = node.parm("coppath").eval()
        elif node_type == "usd":
            path = node.parm("loppath").eval()
        else:
            raise ValueError("ROP node type '%s' is"
                             " not supported." % node_type)

        out_node = hou.node(path)
        instance.data["output_node"] = out_node
