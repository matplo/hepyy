"""Fail a public hepyy release if its pinned native platform wheels are absent."""
import json
import urllib.request

from pathlib import Path
lock = json.loads(Path(__file__).with_name('native-packages.lock.json').read_text())
for name, record in lock['packages'].items():
    version = record['wheel_version']
    with urllib.request.urlopen(f'https://pypi.org/pypi/hepyy-{name}/{version}/json', timeout=30) as response:
        data = json.load(response)
    files = [f['filename'] for f in data['urls'] if not f.get('yanked')]
    for platform in ('manylinux', 'macosx'):
        architectures = ('x86_64',) if platform == 'manylinux' else ('arm64', 'x86_64')
        for arch in architectures:
            assert any(platform in f and f.endswith(arch + '.whl') for f in files), (name, version, platform, arch)
    print(f'Available: hepyy-{name}=={version}, all supported platforms')
