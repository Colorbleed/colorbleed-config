import os

import pyblish.api
import colorbleed.maya.action

from maya import cmds


class ValidateAttributeOverlapWithTransform(pyblish.api.InstancePlugin):
    """Validate whether shape and transform have same attribute names exported.

    This validation checks whether a Shape and its Transform have both the same
    user defined attributes. If those are to be included in the Alembic export
    then the USD Alembic Plug-in will fail to merge the Shape with the
    Transform into a single USD Primitive on load.

    USD Alembic Plug-in code that skips the merge of Transform+Shape:
        https://github.com/PixarAnimationStudios/USD/blob/be1a80f8cb91133ac75e1fc2a2e1832cd10d91c8/pxr/usd/plugin/usdAbc/alembicReader.cpp#L3650-L3659

    Failing to merge on load would mean that under certain circumstances the
    USD Primitive paths of the hierarchy will not remain consistent, which is
    bad. This validator allows to ensure the Alembic to be written will not
    have that particular issue.

    """

    order = colorbleed.api.ValidateContentsOrder
    label = "Transform and Shape Attributes overlap"
    hosts = ["maya"]
    families = ["colorbleed.pointcache",
                "colorbleed.animation"]
    actions = [colorbleed.maya.action.SelectInvalidAction]

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Found invalid nodes: %s" % invalid)

    @classmethod
    def get_invalid(cls, instance):
        # todo: For animation family consider only member nodes of out_SET

        # Get the to be exported attributes
        export_attrs = set(instance.data["attr"])
        export_attr_prefix = instance.data["attrPrefix"]

        if not export_attrs and not export_attr_prefix:
            # No custom attributes will be included in the export anyway
            return

        invalid = []
        for shape in cmds.ls(type=("mesh", "nurbsCurve"),
                             noIntermediate=True):

            shape_attrs = cmds.listAttr(shape, userDefined=True) or []
            if not shape_attrs:
                continue

            transform = cmds.listRelatives(shape,
                                           parent=True,
                                           fullPath=True)[0]
            transform_attrs = cmds.listAttr(transform, userDefined=True) or []
            if not transform_attrs:
                continue

            # Check for any overlap of attribute names
            overlap = set(shape_attrs) & set(transform_attrs)
            if overlap:

                invalid_attrs = []
                for attr in overlap:
                    # Check if this attribute would be included in the export

                    if attr in export_attrs:
                        invalid_attrs.append(attr)
                        continue

                    if any(attr.startswith(prefix) for prefix in
                           export_attr_prefix):
                        invalid_attrs.append(attr)

                if invalid_attrs:
                    cls.log.error("Invalid attributes found: "
                                  "%s %s" % (shape, invalid_attrs))
                    invalid.append(transform)
                    invalid.append(shape)

        return invalid


# Only include this plug-in when CB_ALEMBIC_FORCE_MERGEABLE_SHAPES is set.
ACTIVE = os.environ.get("CB_ALEMBIC_FORCE_MERGEABLE_SHAPES") not in {"0",
                                                                     "False"}
if not ACTIVE:
    print("Skipping ValidateAttributeOverlapWithTransform..")
    del ValidateAttributeOverlapWithTransform
