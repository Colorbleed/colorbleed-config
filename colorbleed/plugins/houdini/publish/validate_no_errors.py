import pyblish.api
import colorbleed.api


def get_errors(node):

    if node.errors():
        # If node already has errors check whether it needs to recook
        # If so, then recook first to see if that solves it.
        if node.needsToCook():
            node.cook()

    return node.errors()


class ValidateNoErrors(pyblish.api.InstancePlugin):
    """Validate the Instance has no current cooking errors."""

    order = colorbleed.api.ValidateContentsOrder
    hosts = ['houdini']
    label = 'Validate no errors'

    def process(self, instance):

        validate_nodes = []

        if len(instance) > 0:
            validate_nodes.append(instance[0])
        output_node = instance.data.get("output_node")
        if output_node:
            validate_nodes.append(output_node)

        for node in validate_nodes:
            self.log.debug("Validating for errors: %s" % node.path())
            errors = get_errors(node)
            if errors:
                self.log.error(errors)
                raise RuntimeError("Node has errors: %s" % node.path())

