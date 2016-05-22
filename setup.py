"""
Setup.py
"""

from setuptools import setup, find_packages

if __name__ == '__main__':
    with \
            open('requirements.in') as requirements, \
            open('test_requirements.in') as test_requirements, \
            open('README.md') as readme:
        setup(
            use_scm_version=True,
            setup_requires=['setuptools_scm'],
            name='django-postgres-composite-types',
            description='Postgres composite types support for Django',
            author='Danielle Madeley',
            author_email='danielle@madeley.id.au',
            url='https://github.com/danni/django-postgres-composite-types',
            long_description=readme.read(),
            classifiers=[
                'License :: OSI Approved :: BSD License',
                'Programming Language :: Python',
                'Programming Language :: Python :: 3',
                'Programming Language :: Python :: 3.4',
                'Programming Language :: Python :: 3.5',
                'Programming Language :: Python :: 3 :: Only',
            ],

            packages=find_packages(exclude=['tests']),
            include_package_data=True,

            install_requires=requirements.readlines(),

            test_suite='tests',
            tests_require=test_requirements.readlines(),
        )
