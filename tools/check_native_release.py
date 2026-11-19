"""Fail a public hepyy release if its pinned native platform wheels are absent."""
import json
import urllib.request

for name, version in [('fastjet', '3.5.1.0'), ('fjcontrib', '1.102.0'), ('pythia8', '8.317.0')]:
    with urllib.request.urlopen(f'https://pypi.org/pypi/hepyy-{name}/{version}/json', timeout=30) as response:
        data = json.load(response)
    files = [f['filename'] for f in data['urls'] if not f.get('yanked')]
    for platform in ('manylinux', 'macosx'):
        architectures = ('x86_64',) if platform == 'manylinux' else ('arm64', 'x86_64')
        for arch in architectures:
            assert any(platform in f and f.endswith(arch + '.whl') for f in files), (name, version, platform, arch)
    print(f'Available: hepyy-{name}=={version}, all supported platforms')
