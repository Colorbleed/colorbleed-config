from collections import defaultdict

import pyblish.api


class ValidateUniqueSubsets(pyblish.api.ContextPlugin):
    """Validate subset is valid and unique among all instances.

    Instances are allowed to overlap in the subset name however they should
    then each not overlap in any way for their families.

    """

    order = pyblish.api.ValidatorOrder
    label = "Validate Subsets Unique"

    def process(self, context):

        subset_families = defaultdict(set)
        subset_instances = defaultdict(list)
        invalid_subsets = []
        invalid_instances = []

        # Ensure each subset has unique instances for families
        for instance in context:

            # Ignore disabled instances
            if not instance.data.get("publish", True) or \
                    not instance.data.get("active", True):
                continue

            if "subset" not in instance.data:
                self.log.warning("Instance is missing subset "
                                 "data: %s" % instance)
                continue

            subset = instance.data.get("subset")
            if not subset:
                self.log.error("Instance has no subset: %s" % instance)
                invalid_instances.append(instance.name)
                continue

            families = instance.data.get("families", [])

            # Backwards compatibility: single family
            family = instance.data.get("family", None)
            if family:
                families.append(family)

            if subset_families[subset].intersection(families):
                # Overlap found
                invalid_subsets.append(subset)

            subset_families[subset].update(families)
            subset_instances[subset].append(instance)

        for subset in invalid_subsets:
            instances = subset_instances[subset]
            instances = [i.name for i in instances]     # use the names
            self.log.error("Subset has multiple instances: "
                           "%s (%s)" % (subset, instances))
            invalid_instances.extend(instances)

        if invalid_instances:
            raise RuntimeError("Invalid instances: %s" % invalid_instances)
