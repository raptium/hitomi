from setuptools import setup, find_packages

setup(
    name = "hitomi",
    version = "0.1",
    packages = find_packages('src'),
    install_requires = ['lxml'],
    
    author = "raptium",
    author_email = "raptium@gmail.com",
    description = "Yet another Readability clone in Python."
)