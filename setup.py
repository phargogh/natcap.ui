from setuptools import setup

setup(
    name='natcap.ui',
    description='UI resources for NatCap projects',
    maintainer='James Douglass',
    maintainer_email='jdouglass@stanford.edu',
    url='https://bitbucket.org/natcap/natcap.ui',
    namespace_packages=['natcap'],
    packages=['natcap', 'natcap.ui'],
    package_dir={'natcap': 'src/natcap'},
    include_package_data=True,
    # PyQt4/5 don't play nicely with pip/pypi.
    install_requires=('natcap.versioner>=0.4.2'),
    setup_requires=('natcap.versioner>=0.4.2',),
    license='GPL',
    test_suite='nose.collector'
)
