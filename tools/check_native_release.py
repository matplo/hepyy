"""Fail a public hepyy release if its pinned native platform wheels are absent."""
import json
import tomllib
import urllib.request

from pathlib import Path
tools = Path(__file__).resolve().parent
lock = json.loads((tools / 'native-packages.lock.json').read_text())
pins = {name: record['wheel_version'] for name, record in lock['packages'].items()}
pyproject = tomllib.loads((tools.parent / 'pyproject.toml').read_text())
extras = pyproject['project']['optional-dependencies']
for name in ('jewel-cpp', 'glauber-cpp'):
    requirement, = extras[name]
    distribution, version = requirement.split('==', 1)
    assert distribution == f'hepyy-{name}'
    pins[name] = version

for name, version in pins.items():
    with urllib.request.urlopen(f'https://pypi.org/pypi/hepyy-{name}/{version}/json', timeout=30) as response:
        data = json.load(response)
    files = [f['filename'] for f in data['urls'] if not f.get('yanked')]
    for platform in ('manylinux', 'macosx'):
        architectures = ('x86_64',) if platform == 'manylinux' else ('arm64', 'x86_64')
        for arch in architectures:
            assert any(platform in f and f.endswith(arch + '.whl') for f in files), (name, version, platform, arch)
    print(f'Available: hepyy-{name}=={version}, all supported platforms')
