import pyblish.api

import avalon.fusion as fusion


class FusionRenderLocal(pyblish.api.InstancePlugin):
    """Render the current Fusion composition locally.

    Extract the result of savers by starting a comp render
    This will run the local render of Fusion.

    """

    order = pyblish.api.ExtractorOrder
    label = "Render Local"
    hosts = ["fusion"]
    families = ["colorbleed.saver.renderlocal"]

    def process(self, instance):
        
        context = instance.context
        current_comp = context.data["currentComp"]
        start_frame = instance.data["startFrame"]
        end_frame = instance.data["endFrame"]

        # todo: implement custom frames collecting for instance
        custom_frames = instance.data.get("frames", None)

        # todo: implement toggle that allows comp-wide to render all savers
        #       at once or one-by-one.
        # Rendering per tool is slower if multiple tools render for a
        # large part the same graph; however it's the only way that allows
        # us to manage them independently and render varying frame ranges.
        run_per_tool = False

        render_kwargs = {
            "Wait": True
        }
        if run_per_tool:
            # Only render the particular saver for this instance
            render_kwargs["Tool"] = instance[0]
        else:
            # If we run all savers at once we only want the InstancePlugin
            # to trigger once. So we store on the Context whether we've run
            # before. If so, skip in the future.
            context = instance.context
            key = "__hasRun{}".format(self.__class__.__name__)
            if context.data.get(key, False):
                return
            else:
                context.data[key] = True

        if custom_frames is not None:
            # Frame Range written as "1..10,20,30,40..50"
            render_kwargs["Frames"] = custom_frames
        else:
            render_kwargs["Start"] = start_frame
            render_kwargs["End"] = end_frame

        self.log.info("Starting render")
        with fusion.comp_lock_and_undo_chunk(current_comp):
            # These kwargs are not expanded with * on purpose because
            # the Render method expects the dictionary like this
            result = current_comp.Render(render_kwargs)

        if not result:
            raise RuntimeError("Comp render failed")
