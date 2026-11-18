import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from hepyy import native
from hepyy.loader import Loader
from hepyy.registry import Registry


@pytest.fixture
def payload(tmp_path, monkeypatch):
    prefix = tmp_path / 'hepyy_fastjet'
    prefix.mkdir()
    manifest = dict(schema_version=1, name='fastjet', version='3.5.1',
                    distribution_version='3.5.1.0', headers=['fastjet/PseudoJet.hh'],
                    libraries=['fastjet'], cppyy_namespace='fastjet', depends_on=[],
                    abi='test-abi')
    (prefix / 'manifest.json').write_text(json.dumps(manifest))
    dist = Mock(version='3.5.1.0')
    dist.locate_file.side_effect = lambda name: tmp_path / name
    monkeypatch.setattr(native.metadata, 'distribution', lambda name: dist)
    return prefix


@pytest.fixture
def loader(tmp_path, monkeypatch):
    import hepyy.loader as module
    reg = Registry(tmp_path / 'missing' / 'registry.json')
    monkeypatch.setattr(module, 'get_registry', lambda: reg)
    obj = Loader()
    obj._loaded = set()
    obj._loaded_records = {}
    obj._setup_cppyy = Mock()
    obj._inject_proxy_module = Mock()
    return obj, reg


def test_manifest_discovery_does_not_write_registry(payload, loader):
    obj, reg = loader
    obj.load('fastjet')
    assert not reg._path.exists()
    assert obj._loaded_records['fastjet']['provider'] == 'wheel'
    assert obj._setup_cppyy.call_args.args[2] == ['fastjet']


def test_version_filter_and_schema(payload):
    assert native.wheel_record('fastjet', '3.4.0') is None
    assert native.wheel_record('unknown') is None
    (payload / 'manifest.json').write_text('{"schema_version": 99}')
    with pytest.raises(RuntimeError, match='Invalid'):
        native.wheel_record('fastjet')


def test_metadata_version_mismatch(payload):
    path = payload / 'manifest.json'
    data = json.loads(path.read_text())
    data['distribution_version'] = '3.5.1.99'
    path.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match='version mismatch'):
        native.wheel_record('fastjet')


def test_source_registry_precedes_wheel(payload, loader):
    obj, reg = loader
    reg.register('fastjet', '3.5.1', dict(version='3.5.1', prefix='/source',
                  include_dir='/source/include', lib_dir='/source/lib'))
    obj.load('fastjet')
    assert obj._loaded_records['fastjet']['prefix'] == '/source'


def test_shell_precedes_wheel(payload, loader, monkeypatch):
    obj, _ = loader
    monkeypatch.setenv('HEPYY_LOADED_FASTJET', '3.5.1')
    monkeypatch.setenv('HEPYY_LOADED_FASTJET_PREFIX', '/shell')
    obj.load('fastjet')
    assert obj._loaded_records['fastjet']['prefix'] == '/shell'


@pytest.mark.parametrize('dependency', [None, {'provider': 'source', 'abi': 'x'},
                                         {'provider': 'wheel', 'abi': 'wrong'}])
def test_reject_mixed_abi(dependency):
    with pytest.raises(RuntimeError, match='requires fastjet wheel ABI'):
        native.validate_dependencies(dict(name='fjcontrib', requires_native={'fastjet': 'x'}),
                                     {'fastjet': dependency})


def test_matching_abi():
    native.validate_dependencies(dict(name='fjcontrib', requires_native={'fastjet': 'x'}),
                                 {'fastjet': {'provider': 'wheel', 'abi': 'x'}})


def test_wheel_failure_is_not_marked_loaded(payload, loader):
    obj, _ = loader
    obj._setup_cppyy.side_effect = RuntimeError('dlopen failed')
    with pytest.raises(RuntimeError, match='dlopen'):
        obj.load('fastjet')
    assert not obj._loaded


def test_missing_library_fails_closed(tmp_path, monkeypatch):
    obj = Loader()
    monkeypatch.setattr(obj, '_preload_cppyy_deps', lambda: None)
    monkeypatch.setitem(sys.modules, 'cppyy', Mock())
    with pytest.raises(FileNotFoundError, match='Native wheel'):
        obj._setup_cppyy(dict(provider='wheel', include_dir=str(tmp_path), lib_dir=str(tmp_path)),
                         [], ['missing'], False)


def test_conda_cppyy_not_shadowed(tmp_path, monkeypatch):
    import importlib.util
    (tmp_path / 'conda-meta').mkdir()
    monkeypatch.delitem(sys.modules, 'cppyy', raising=False)
    monkeypatch.setattr(sys, 'prefix', str(tmp_path))
    monkeypatch.setattr(importlib.util, 'find_spec', lambda _: object())
    before = list(sys.path)
    Loader()._ensure_cppyy_on_syspath()
    assert sys.path == before


@pytest.mark.parametrize('already_loaded', [False, True])
def test_loader_rejects_mixed_fastjet_before_dlopen(loader, monkeypatch, already_loaded):
    obj, reg = loader
    source = dict(version='3.5.1', prefix='/source', include_dir='/source/include', lib_dir='/source/lib')
    if already_loaded:
        obj._loaded.add('fastjet')
        obj._loaded_records['fastjet'] = source
    else:
        reg.register('fastjet', '3.5.1', source)
    contrib = dict(provider='wheel', name='fjcontrib', version='1.102', prefix='/wheel',
                   headers=[], libraries=['fastjetcontribfragile'], depends_on=['fastjet'],
                   requires_native={'fastjet': 'test-abi'})
    monkeypatch.setattr(native, 'wheel_record', lambda name, version=None: contrib)
    with pytest.raises(RuntimeError, match='requires fastjet wheel ABI'):
        obj.load('fjcontrib')
    obj._setup_cppyy.assert_not_called()
    assert 'fjcontrib' not in obj._loaded
