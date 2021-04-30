import os

import pyblish.api


def get_comp_render_range(comp):
    """Return comp's start and end render range."""
    comp_attrs = comp.GetAttrs()
    start = comp_attrs["COMPN_RenderStart"]
    end = comp_attrs["COMPN_RenderEnd"]

    # Whenever render ranges are undefined fall back
    # to the comp's global start and end
    if start == -1000000000:
        start = comp_attrs["COMPN_GlobalEnd"]
    if end == -1000000000:
        end = comp_attrs["COMPN_GlobalStart"]

    return start, end


def get_value(tool, attribute, default=None):
    value = tool.GetInput(attribute)
    if value is None:
        return default
    else:
        return value


class CollectInstances(pyblish.api.ContextPlugin):
    """Collect Fusion saver instances

    This additionally stores the Comp start and end render range in the
    current context's data as "startFrame" and "endFrame".

    """

    order = pyblish.api.CollectorOrder
    label = "Collect Instances"
    hosts = ["fusion"]

    def process(self, context):
        """Collect all image sequence tools"""

        from avalon.fusion.lib import get_frame_path
        
        asset = os.environ["AVALON_ASSET"]  # todo: not a constant
        self.log.info("Current asset: %s" % asset)
        
        comp = context.data["currentComp"]

        # Get all savers in the comp
        tools = comp.GetToolList(False).values()
        savers = [tool for tool in tools if tool.ID == "Saver"]

        start, end = get_comp_render_range(comp)

        for tool in savers:
            path = tool["Clip"][comp.TIME_UNDEFINED]

            tool_attrs = tool.GetAttrs()
            active = not tool_attrs["TOOLB_PassThrough"]

            if not path:
                self.log.warning("Skipping saver because it "
                                 "has no path set: {}".format(tool.Name))
                continue


            filename = os.path.basename(path)
            head, padding, tail = get_frame_path(filename)
            ext = os.path.splitext(path)[1]
            assert tail == ext, ("Tail does not match %s" % ext)
            subset = head.rstrip("_. ")   # subset is head of the filename

            # Include start and end render frame in label
            label = ("{subset} ({asset}) "
                     "[{start}-{end}]").format(subset=subset,
                                               asset=asset,
                                               start=int(start),
                                               end=int(end))

            icon = "files-o"
            publish = get_value(tool, "avalon_Publish", default=True)
            if not publish:
                icon = "bolt"

            instance = context.create_instance(subset)
            instance.data.update({
                "asset": asset,
                "subset": subset,
                "path": path,
                "outputDir": os.path.dirname(path),
                "ext": ext,  # todo: should be redundant
                "label": label,
                "families": ["colorbleed.saver"],
                "family": "colorbleed.saver",
                "active": active,
                "publish": active,  # backwards compatibility
                
                "icon": icon,

                # Frame ranges
                "startFrame": start,
                "endFrame": end,
                # todo: implement custom frame list

                # We allow preview savers to Render but skip publishing
                # using a custom attribute
                "performPublish": publish
            })

            instance.append(tool)

            self.log.info("Found: \"%s\" " % path)

        # Sort/grouped by family (preserving local index)
        context[:] = sorted(context, key=self.sort_by_family)

        return context

    def sort_by_family(self, instance):
        """Sort by family"""
        return instance.data.get("families", instance.data.get("family"))
