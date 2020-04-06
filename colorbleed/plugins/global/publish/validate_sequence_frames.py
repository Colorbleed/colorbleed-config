import pyblish.api

from avalon.vendor import clique


def get_collections(files):
    """Return the file collection and its remainder"""

    # Support filenames like: projectX_shot01_0010.tiff with this regex
    pattern = r"(?P<index>(?P<padding>0*)\d+)\.\D+\d?$"
    collections, remainder = clique.assemble(files,
                                             patterns=[pattern],
                                             minimum_items=1)
    return collections, remainder


class ValidateSequenceFrames(pyblish.api.InstancePlugin):
    """Ensure the sequence of frames is complete

    The files found in the folder are checked against the startFrame and
    endFrame of the instance. If the first or last file is not
    corresponding with the first or last frame it is flagged as invalid.
    """

    order = pyblish.api.ValidatorOrder
    label = "Validate Sequence Frames"
    families = ["colorbleed.imagesequence"]
    hosts = ["shell"]

    def process(self, instance):

        filenames = instance.data["files"]
        assert isinstance(filenames[0], (list, tuple))
        assert len(filenames) == 1, \
            "Image Sequence instance should have one collection"
        collections, remainder = get_collections(filenames[0])

        assert len(collections) == 1, \
            "Did not find a single collection: {0}".format(collections)
        assert not remainder, "Found remaining files: {0}".format(remainder)

        collection = collections[0]
        self.log.info(collection)

        frames_explicit = instance.data.get("frames", None)
        if frames_explicit is None:
            # Validate start-end with no holes
            frames = list(collection.indexes)
            current_range = (frames[0], frames[-1])
            required_range = (instance.data["startFrame"],
                              instance.data["endFrame"])

            if current_range != required_range:
                raise ValueError("Invalid frame range: {0} - "
                                 "expected: {1}".format(current_range,
                                                        required_range))

            missing = collection.holes().indexes
            assert not missing, "Missing frames: %s" % (missing,)

        else:
            # Explicit frames (custom frames list)
            missing = set(frames_explicit) - collection.indexes
            assert not missing, "Missing frames: %s" % (sorted(missing),)

