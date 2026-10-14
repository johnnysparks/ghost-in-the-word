from setuptools import find_packages, setup


setup(
    name="ghost-in-the-word",
    version="0.1.0",
    description="Corpus and alignment tools for Bible translation comparison",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.9",
)
