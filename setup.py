from setuptools import setup

setup(
    name="HITSZ-Connect-Verge",
    version="1.0",
    description="A GUI application to connect to service of HITSZ, powered by zju-connect.",
    author="Kowyo",
    packages=[],
    include_package_data=True,
    install_requires=[
        "PySide6",
        "keyring"
    ],
)
