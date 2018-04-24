import pyblish.api


class CollectColorbleedComment(pyblish.api.ContextPlugin):
    """This plug-ins displays the comment dialog box per default"""

    label = "Collect Comment"
    order = pyblish.api.CollectorOrder

    def process(self, context):
        context.data["comment"] = ""
