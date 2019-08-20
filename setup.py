"""The colorbleed production pipeline"""

import os
from setuptools import setup, find_packages


classifiers = [
    "Development Status :: 5 - Production/Stable",
    "License :: OSI Approved :: MIT License",
    "Intended Audience :: Developers",
    "Operating System :: OS Independent",
    "Programming Language :: Python",
    "Programming Language :: Python :: 2",
    "Programming Language :: Python :: 2.7",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.6",
    "Programming Language :: Python :: 3.7",
    "Topic :: Utilities",
    "Topic :: Software Development",
    "Topic :: Software Development :: Libraries :: Python Modules",
]

exclude = [
    "__pycache__",
]

here = os.path.dirname(__file__)
package_dir = os.path.join(here, "colorbleed")
version = None

# Read version from file, to avoid importing anything
mod = {}
with open(os.path.join(package_dir, "version.py")) as f:
    exec(compile(f.read(), f.name, 'exec'), mod)
    version = mod["version"]

assert len(version.split(".")) == 3, version

package_data = []
for base, dirs, files in os.walk(package_dir):
    dirs[:] = [d for d in dirs if d not in exclude]
    relpath = os.path.relpath(base, package_dir)
    basename = os.path.basename(base)

    for fname in files:
        if any(fname.endswith(pat) for pat in exclude):
            continue

        fname = os.path.join(relpath, fname)
        package_data += [fname]

setup(
    name="avalon-colorbleed",
    version=version,
    url="https://github.com/Colorbleed/colorbleed-config",
    author="Roy Nieterau",
    author_email="roy@colorbleed.com",
    license="MIT",
    zip_safe=False,
    packages=find_packages(),
    package_data={
        "colorbleed": package_data,
    },
    classifiers=classifiers,
    install_requires=[
        "pyblish-base>=1.5",
        "avalon-core>=5.2",
    ],
    python_requires=">2.7, <4",
)
