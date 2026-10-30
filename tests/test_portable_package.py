"""Validate private migration bundles before any Docker/database mutation."""
import hashlib
import gzip
import json
import shutil
import subprocess
from pathlib import Path
import pytest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/portable.ps1'
SHELL=shutil.which('pwsh') or shutil.which('powershell.exe')
pytestmark=pytest.mark.skipif(not SHELL,reason='PowerShell is needed for Windows migration helper verification')

def bundle(tmp_path, *, compressed=False):
    archive='images.tar.gz' if compressed else 'images.tar'
    paths=[archive,'project/compose.yaml','project/.env','project/scripts/portable.ps1','database/local.dump','config/local/model-config.key']
    files=[]
    for name in paths:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(gzip.compress(b'isolated-verification-only') if name==archive and compressed else b'isolated-verification-only')
        files.append(dict(path=name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    manifest=dict(format=2 if compressed else 1,platform='linux/amd64',stacks=['local'],files=files)
    if compressed: manifest.update(image_archive=archive,key_stacks=['local'])
    return manifest

def verify(root,manifest):
    (root/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return subprocess.run([SHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(SCRIPT),'-Action','Verify','-PackagePath',str(root)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)

def test_valid_bundle_can_be_checked_without_docker(tmp_path):
    result=verify(tmp_path,bundle(tmp_path));assert result.returncode==0,result.stderr

def test_changed_database_dump_is_rejected(tmp_path):
    manifest=bundle(tmp_path);(tmp_path/'database/local.dump').write_bytes(b'corrupt-transfer')
    assert verify(tmp_path,manifest).returncode!=0

def test_path_traversal_is_rejected_before_reading_outside_bundle(tmp_path):
    manifest=bundle(tmp_path);manifest['files'].insert(0,dict(path='../not-in-package',sha256='a'*64))
    assert verify(tmp_path,manifest).returncode!=0

def test_unlisted_model_key_cannot_be_trusted_even_when_file_exists(tmp_path):
    manifest=bundle(tmp_path);manifest['files']=[f for f in manifest['files']if not f['path'].endswith('model-config.key')]
    assert verify(tmp_path,manifest).returncode!=0

def test_duplicate_stack_cannot_trigger_a_second_restore(tmp_path):
    manifest=bundle(tmp_path);manifest['stacks']=['local','local']
    assert verify(tmp_path,manifest).returncode!=0


def test_compressed_bundle_is_supported_without_docker(tmp_path):
    result=verify(tmp_path,bundle(tmp_path,compressed=True));assert result.returncode==0,result.stderr


def test_compressed_archive_name_cannot_escape_package(tmp_path):
    manifest=bundle(tmp_path,compressed=True);manifest['image_archive']='../images.tar.gz'
    assert verify(tmp_path,manifest).returncode!=0


def test_compressed_image_must_be_in_verified_file_list(tmp_path):
    manifest=bundle(tmp_path,compressed=True);manifest['files']=[f for f in manifest['files']if f['path']!='images.tar.gz']
    assert verify(tmp_path,manifest).returncode!=0


def test_environment_only_configuration_does_not_require_invented_key(tmp_path):
    manifest=bundle(tmp_path,compressed=True);manifest['key_stacks']=[]
    manifest['files']=[f for f in manifest['files']if not f['path'].endswith('model-config.key')]
    (tmp_path/'config/local/model-config.key').unlink()
    result=verify(tmp_path,manifest);assert result.returncode==0,result.stderr


def test_new_bundle_must_declare_its_model_key_inventory(tmp_path):
    manifest=bundle(tmp_path,compressed=True);del manifest['key_stacks']
    assert verify(tmp_path,manifest).returncode!=0


def test_model_key_inventory_cannot_reference_another_installation(tmp_path):
    manifest=bundle(tmp_path,compressed=True);manifest['key_stacks']=['preview']
    assert verify(tmp_path,manifest).returncode!=0
