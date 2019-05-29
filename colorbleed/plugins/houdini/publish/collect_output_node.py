import pyblish.api


class CollectOutputNodePath(pyblish.api.InstancePlugin):
    """Collect the out node's SOP/COP Path value."""

    order = pyblish.api.CollectorOrder
    families = ["colorbleed.pointcache",
                "colorbleed.vdbcache",
                "colorbleed.imagesequence"]
    hosts = ["houdini"]
    label = "Collect Output Node Path"

    def process(self, instance):

        import hou

        node = instance[0]

        # Get sop path
        node_type = node.type().name()
        if node_type == "geometry":
            path_parm = "soppath"
        elif node_type == "alembic":
            path_parm = "sop_path"
        elif node_type == "comp":
            path_parm = "coppath"
        else:
            raise ValueError("ROP node type '%s' is not supported." % node_type)

        path = node.parm(path_parm).eval()
        out_node = hou.node(path)

        instance.data["output_node"] = out_node
