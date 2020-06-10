import pyblish.api
import avalon.api


class ValidateMatchCurrentAsset(pyblish.api.InstancePlugin):
    """Validates instance 'asset' is set to the current asset.

    This is *not* a hard requirement so this validation is Optional.
    However, since willfully publishing to another asset is so extremely
    rare we catch most User errors.

    If you explicitly want to publish to another asset then you will
    need to disable this Validation prior to publish, toggle it off.

    Requires:
        instance ->     asset (str)

    """

    order = pyblish.api.ValidatorOrder - 0.4
    families = ["*"]
    label = "Match current Asset"
    optional = True

    def process(self, instance):

        asset = instance.data.get("asset", None)

        if asset is None:
            self.log.warning("No asset set for the instance, ignoring..")
            return

        context_asset = avalon.api.Session["AVALON_ASSET"]
        if asset != context_asset:
            raise RuntimeError(
                "Instance asset publishes to a different asset:"
                " %s (current asset: %s)" % (asset, context_asset)
            )
