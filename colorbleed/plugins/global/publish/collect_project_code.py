import pyblish.api
import avalon.io as io

class CollectProjectCode(pyblish.api.ContextPlugin):
    """Collect the Project code from database project.data["config"]

    If project code not present in project.data it will fall back to None.

    """

    label = "Collect Project Code"
    order = pyblish.api.CollectorOrder

    def process(self, context):

        project = io.find_one({"type": "project"},
                              projection={"data.code": True})
        if not project:
            raise RuntimeError("Can't find current project in database.")

        code = project["data"].get("code", None)
        self.log.info("Collected project code: %s" % code)
        context.data["code"] = code
