import maya.cmds as cmds

import pyblish.api
import colorbleed.api
import colorbleed.maya.lib as lib


class ValidateRedshiftSingleBeautyAOV(pyblish.api.InstancePlugin):
    """Validate Beauty AOV does not exist more than once.
    
    Redshift will ignore multiple Beauty AOVs at rendertime and
    output only one of the AOVs - thus resulting in a different
    expected amount of output files. Here we validate only single
    beauty AOV is active in a renderlayer.
    
    """
    # TODO: Is it possible to render two Beauty AOVs one set to "All" and other set to "Remainder"?

    order = pyblish.api.ValidatorOrder
    label = "Single Beauty AOV"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer.redshift"]


    def process(self, instance):

        if instance.data.get("renderer", None) != "redshift":
            # If not rendering with Redshft, ignore..
            return
            
        layer = instance.data["setMembers"]
        
        aovs = cmds.ls(type="RedshiftAOV")
        beauty_aovs = []
        for node in aovs:
        
            
            aov_type = cmds.getAttr(node + ".aovType")
            if aov_type != "Beauty":
                continue
            
            enabled = lib.get_attr_in_layer("{}.enabled".format(node),
                                            layer=layer)
            if not enabled:
                continue
                
            beauty_aovs.append(node)
            
        if len(beauty_aovs) > 1:
            names = [cmds.getAttr(node + ".name") for node in beauty_aovs]
            raise RuntimeError("Multiple Redshift Beauty AOVs active. "
                               "Remove or disable one of: {}".format(", ".join(names)))
            