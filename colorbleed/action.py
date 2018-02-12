# absolute_import is needed to counter the `module has no cmds error` in Maya
from __future__ import absolute_import
import pyblish.api


def get_errored_instances_from_context(context):

    instances = list()
    for result in context.data["results"]:
        if result["instance"] is None:
            # When instance is None we are on the "context" result
            continue

        if result["error"]:
            instances.append(result["instance"])

    return instances


def get_errored_plugins_from_data(context):
    """Get all failed validation plugins

    Args:
        context (object):

    Returns:
        list of plugins which failed during validation

    """

    plugins = list()
    results = context.data.get("results", [])
    for result in results:
        if result["success"] is True:
            continue
        plugins.append(result["plugin"])

    return plugins


class RepairAction(pyblish.api.Action):
    """Repairs the action

    To process the repairing this requires a static `repair(instance)` method 
    is available on the plugin.

    """
    label = "Repair"
    on = "failed"  # This action is only available on a failed plug-in
    icon = "wrench"  # Icon from Awesome Icon

    def process(self, context, plugin):

        if not hasattr(plugin, "repair"):
            raise RuntimeError("Plug-in does not have repair method.")

        # Get the errored instances
        self.log.info("Finding failed instances..")
        errored_instances = get_errored_instances_from_context(context)

        # Apply pyblish.logic to get the instances for the plug-in
        instances = pyblish.api.instances_by_plugin(errored_instances, plugin)
        for instance in instances:
            plugin.repair(instance)


class RepairContextAction(pyblish.api.Action):
    """Repairs the action

    To process the repairing this requires a static `repair(instance)` method 
    is available on the plugin.

    """
    label = "Repair Context"
    on = "failed"  # This action is only available on a failed plug-in

    def process(self, context, plugin):

        if not hasattr(plugin, "repair"):
            raise RuntimeError("Plug-in does not have repair method.")

        # Get the errored instances
        self.log.info("Finding failed instances..")
        errored_plugins = get_errored_plugins_from_data(context)

        # Apply pyblish.logic to get the instances for the plug-in
        if plugin in errored_plugins:
            self.log.info("Attempting fix ...")
            plugin.repair()


class SelectInvalidAction(pyblish.api.Action):
    """Select invalid nodes in Maya when plug-in failed.

    To retrieve the invalid nodes this assumes a static `get_invalid()`
    method is available on the plugin.

    """
    label = "Select invalid"
    on = "failed"  # This action is only available on a failed plug-in
    icon = "search"  # Icon from Awesome Icon

    def process(self, context, plugin):

        try:
            from maya import cmds
        except ImportError:
            raise ImportError("Current host is not Maya")

        errored_instances = get_errored_instances_from_context(context)

        # Apply pyblish.logic to get the instances for the plug-in
        instances = pyblish.api.instances_by_plugin(errored_instances, plugin)

        # Get the invalid nodes for the plug-ins
        self.log.info("Finding invalid nodes..")
        invalid = list()
        for instance in instances:
            invalid_nodes = plugin.get_invalid(instance)
            if invalid_nodes:
                if isinstance(invalid_nodes, (list, tuple)):
                    invalid.extend(invalid_nodes)
                else:
                    self.log.warning("Plug-in returned to be invalid, "
                                     "but has no selectable nodes.")

        # Ensure unique (process each node only once)
        invalid = list(set(invalid))

        if invalid:
            self.log.info("Selecting invalid nodes: %s" % ", ".join(invalid))
            cmds.select(invalid, replace=True, noExpand=True)
        else:
            self.log.info("No invalid nodes found.")
            cmds.select(deselect=True)


class GenerateUUIDsOnInvalidAction(pyblish.api.Action):
    """Generate UUIDs on the invalid nodes in the instance.

    Invalid nodes are those returned by the plugin's `get_invalid` method.
    As such it is the plug-in's responsibility to ensure the nodes that
    receive new UUIDs are actually invalid.

    Requires:
        - instance.data["asset"]

    """

    label = "Regenerate UUIDs"
    on = "failed"  # This action is only available on a failed plug-in
    icon = "wrench"  # Icon from Awesome Icon

    def process(self, context, plugin):

        self.log.info("Finding bad nodes..")

        # Get the errored instances
        errored_instances = []
        for result in context.data["results"]:
            if result["error"] is not None and result["instance"] is not None:
                if result["error"]:
                    instance = result["instance"]
                    errored_instances.append(instance)

        # Apply pyblish logic to get the instances for the plug-in
        instances = pyblish.api.instances_by_plugin(errored_instances, plugin)

        # Get the nodes from the all instances that ran through this plug-in
        all_invalid = []
        for instance in instances:
            invalid = plugin.get_invalid(instance)
            if invalid:

                self.log.info("Fixing instance {}".format(instance.name))
                self._update_id_attribute(instance, invalid)

                all_invalid.extend(invalid)

        if not all_invalid:
            self.log.info("No invalid nodes found.")
            return

        all_invalid = list(set(all_invalid))
        self.log.info("Generated ids on nodes: {0}".format(all_invalid))

    def _update_id_attribute(self, instance, nodes):
        """Delete the id attribute

        Args:
            instance: The instance we're fixing for
            nodes (list): all nodes to regenerate ids on
        """

        import colorbleed.maya.lib as lib
        import avalon.io as io

        asset = instance.data['asset']
        asset_id = io.find_one({"name": asset, "type": "asset"},
                               projection={"_id": True})['_id']
        for node, _id in lib.generate_ids(nodes, asset_id=asset_id):
            lib.set_id(node, _id, overwrite=True)
