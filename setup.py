from setuptools import setup, find_packages

setup(
    name="nano_local",
    version="0.1.5",
    packages=find_packages(),
    install_requires=[
        "tomli", "tomli-w", "requests", "oyaml", "ed25519-blake2b", "gmpy2",
        "aiohttp", "pytest", "pytest-html", "nanolib", "extradict"
    ],
    author="gr0vity",
    description="A simple way to locally create a network of nano_nodes",
)