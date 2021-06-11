import pyblish.api
import colorbleed.api
import os

from collections import defaultdict


class ValidateTransfers(pyblish.api.InstancePlugin):
    """Validates resources all transfer to a unique location.
    
    When raising errors there are source files on multiple locations
    that end up on the same destination, essentially overwriting each other.
    
    For example "textures" with the same filenames from different source
    folders will be considered invalid. For textures the recommended way
    to debug is to look for similar filenames using:
        Windows > General Editors > File Path Editor 
    
    """

    order = colorbleed.api.ValidateContentsOrder
    label = "Transfers"

    def process(self, instance):

        transfers = instance.data.get("transfers", [])
        if not transfers:
            return

        # Collect all destination with its sources
        collected = defaultdict(set)
        for source, destination in transfers:

            # Use normalized paths in comparison and ignore case sensitivity
            source = os.path.normpath(source).lower()
            destination = os.path.normpath(destination).lower()

            collected[destination].add(source)
            
        def nice_path(path):
            return path.replace("\\", "/")

        invalid_destinations = list()
        for destination, sources in collected.items():
            if len(sources) > 1:
                invalid_destinations.append(destination)
                
                # Log the issue to the user
                self.log.error("Non-unique file transfer for destination: "
                               "{0}".format(nice_path(destination))
                for source in sources:
                    self.log.warning("Source: %s" % nice_path(source)) 

        if invalid_destinations:
            raise RuntimeError("Invalid transfers in queue.")
