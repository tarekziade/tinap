# encoding: utf8
import os
import sys
from setuptools import setup, find_packages


with open("README.rst") as f:
    README = f.read()

if sys.platform == "win32":
    install_requires = ["pywin32"]
else:
    install_requires = []


setup(name="tinap",
      version="0.2",
      author="Tarek Ziadé",
      author_email="tarek@mozilla.com",
      url="https://github.com/tarekziade/tinap",
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
