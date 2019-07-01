import os
from setuptools import setup, find_packages


with open("README.rst") as f:
    README = f.read()

install_requires = []


setup(name="tinap",
      version="0.1",
      packages=find_packages(),
      description="Port forwarding with traffic shaping",
      long_description=README,
      include_package_data=True,
      zip_safe=False,
      install_requires=install_requires,
      entry_points="""
      [console_scripts]
      tinap = tinap:main
      """)
