from setuptools import setup, find_packages

with open('README.rst') as f:
    long_description = ''.join(f.readlines())

setup(
    name='labelord_suchama4',
    version='0.3',
    keywords='github labels management replication',
    description='Simple CLI and WEB tools for managing GitHub labels',
    long_description=long_description,
    author='Marek Suchánek',
    author_email='suchama4@fit.cvut.cz',
    license='MIT',
    url='https://github.com/MarekSuchanek/labelord',
    zip_safe=False,
    packages=find_packages(),
    package_data={
        'labelord': [
            'static/*.js',
            'static/*.css',
            'templates/*.html',
        ]
    },
    entry_points={
        'console_scripts': [
            'labelord = labelord:main',
        ]
    },
    install_requires=[
        'configparser',
        'click',
        'Flask',
        'requests',
    ],
    setup_requires=[
        'pytest-runner',
    ],
    tests_require=[
        'betamax',
        'betamax-serializers',
        'flexmock',
        'pytest',
        'pytest-flake8',
        'pytest-sugar',
        'pytest-cov',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Framework :: Flask',
        'Intended Audience :: Developers',
        'Intended Audience :: Education',
        'Intended Audience :: Information Technology',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Software Development',
        'Topic :: Utilities',
    ],
)
