import os
import pyblish.api

# Only do this whenever PYBLISH_QML_POST_COLLECT is used..
post_collector_order = os.environ.get("PYBLISH_QML_POST_COLLECT", None)
if post_collector_order is not None:

    class FixPostCollectorBug(pyblish.api.ContextPlugin):
        """Fix Post Collector bug

        Without this fix the first plug-in that should not trigger in the
        Post Collector range due to deactivated instances will still
        trigger until it processes one that should run.

        Also see:
            https://github.com/pyblish/pyblish-qml/pull/356

        """

        order = float(post_collector_order)
        label = "Post Collector bug workaround"

        def process(self, context):
            pass
