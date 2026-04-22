from setuptools import setup, find_packages

def read_requirements():
    with open('requirements.txt', 'r') as req:
        content = req.read()
        requirements = content.split('\n')
    return [r for r in requirements if r and not r.startswith('#')]

setup(
    name="tgcf",
    version="1.1.8",
    packages=find_packages(),
    install_requires=read_requirements(),
    entry_points={
        'console_scripts': [
            'tgcf=tgcf.cli:app',
        ],
    },
)
