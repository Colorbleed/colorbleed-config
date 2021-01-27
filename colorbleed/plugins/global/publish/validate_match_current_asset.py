import pyblish.api
import avalon.api
from colorbleed.action import get_errored_instances_from_context

# Get the host registered host name in Avalon
HOST = avalon.api.registered_host().__name__.rsplit(".", 1)[-1]


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


class RepairCurrentAsset(pyblish.api.Action):
    label = "Repair"
    on = "failed"
    icon = "wrench"

    def process(self, context, plugin):

        # Get the errored instances
        self.log.info("Finding failed instances..")
        errored_instances = get_errored_instances_from_context(context)

        # Apply pyblish.logic to get the instances for the plug-in
        instances = pyblish.api.instances_by_plugin(errored_instances,
                                                    plugin)

        repair_fn = {
            "maya": self.repair_maya,
            "houdini": self.repair_houdini
        }.get(HOST)

        for instance in instances:
            repair_fn(instance)

    def repair_maya(self, instance):
        from maya import cmds
        asset = avalon.api.Session["AVALON_ASSET"]
        node = instance.data['name']
        cmds.setAttr(node + ".asset", asset, type="string")

    def repair_houdini(self, instance):
        asset = avalon.api.Session["AVALON_ASSET"]
        node = instance[0]
        node.setParms({"asset": asset})


# Allow to repair in Maya or Houdini
if HOST in {"maya", "houdini"}:
    ValidateMatchCurrentAsset.actions = [RepairCurrentAsset]
