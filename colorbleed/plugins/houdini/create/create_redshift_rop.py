import hou

from avalon import houdini


class CreateRedshiftROP(houdini.Creator):
    """Redshift ROP"""

    label = "Redshift ROP"
    family = "redshift_rop"
    icon = "magic"
    defaults = ["master"]

    def __init__(self, *args, **kwargs):
        super(CreateRedshiftROP, self).__init__(*args, **kwargs)

        # Clear the family prefix from the subset
        subset = self.data["subset"]
        subset_no_prefix = subset[len(self.family):]
        subset_no_prefix = subset_no_prefix[0].lower() + subset_no_prefix[1:]
        self.data["subset"] = subset_no_prefix

        # Remove the active, we are checking the bypass flag of the nodes
        self.data.pop("active", None)

        self.data.update({"node_type": "Redshift_ROP"})

    def process(self):
        instance = super(CreateRedshiftROP, self).process()

        prefix = '$HIP/render/$HIPNAME/`chs("subset")`.$F4.exr'
        parms = {
            # Render frame range
            "trange": 1,

            # Redshift ROP settings
            "RS_outputFileNamePrefix": prefix,
            "RS_outputMultilayerMode": 0,           # no multi-layered exr
            "RS_outputBeautyAOVSuffix": "beauty"
        }
        instance.setParms(parms)

        # Lock some Avalon attributes
        to_lock = ["family", "id"]
        for name in to_lock:
            parm = instance.parm(name)
            parm.lock(True)
