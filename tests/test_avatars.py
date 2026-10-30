import base64
from io import BytesIO
from uuid import UUID

import pytest
from PIL import Image
from sqlalchemy import select

from app.account_models import UserAvatar
from app.avatars import normalize_avatar, AvatarConflict
from app.models import User, AuditLog
from app.account_routes import Invite
from test_account_lifecycle import setup, reg


def raster(format='PNG', size=(320, 240), metadata=False):
    image = Image.new('RGB', size, '#416dd0')
    extra = {}
    if metadata:
        exif = Image.Exif()
        exif[274] = 6
        exif[271] = 'synthetic metadata - not a real camera'
        extra['exif'] = exif
        extra['comment'] = b'not retained'
    output = BytesIO()
    image.save(output, format=format, **extra)
    return f'data:image/{format.lower().replace("jpg", "jpeg")};base64,' + base64.b64encode(output.getvalue()).decode()


@pytest.mark.parametrize('format', ['PNG', 'JPEG', 'WEBP'])
def test_canonical_square_raster(format):
    result = normalize_avatar(raster(format))
    assert len(result) < 200_000
    with Image.open(BytesIO(result)) as image:
        assert image.format == 'JPEG' and image.size == (256, 256)


def test_metadata_and_transparency_stripped():
    result = normalize_avatar(raster('JPEG', metadata=True))
    with Image.open(BytesIO(result)) as image:
        assert not image.getexif() and 'comment' not in image.info and 'icc_profile' not in image.info
    transparent = Image.new('RGBA', (128, 128), (255, 0, 0, 0))
    output = BytesIO(); transparent.save(output, format='PNG')
    result = normalize_avatar('data:image/png;base64,' + base64.b64encode(output.getvalue()).decode())
    with Image.open(BytesIO(result)) as image:
        assert image.getpixel((128, 128)) == (255, 255, 255)


@pytest.mark.parametrize('value', [
    'https://example.invalid/photo.jpg',
    'data:image/svg+xml;base64,PHN2Zy8+',
    'data:image/png;base64,not-a-valid-image',
    'data:image/jpeg;base64,' + base64.b64encode(b'<script>alert(1)</script>').decode(),
    'data:image/png;base64,' + 'A' * 280_000,
], ids=['remote-url', 'svg', 'bad-base64', 'html-payload', 'oversized'])
def test_reject_invalid_images(value):
    with pytest.raises(ValueError): normalize_avatar(value)


def test_dimensions_animation_and_mime_checked():
    for size in [(10, 10), (2049, 2049), (4097, 32)]:
        with pytest.raises(ValueError): normalize_avatar(raster(size=size))
    with pytest.raises(ValueError): normalize_avatar(raster('PNG').replace('image/png', 'image/jpeg'))
    output = BytesIO()
    Image.new('RGB', (100, 100), 'red').save(output, 'WEBP', save_all=True, append_images=[Image.new('RGB', (100, 100), 'blue')], duration=100)
    with pytest.raises(ValueError): normalize_avatar('data:image/webp;base64,' + base64.b64encode(output.getvalue()).decode())


def test_all_roles_persistence_and_isolation(setup):
    svc, sessions, admin, teacher, course, auth, client = setup
    inv = svc.create_invite(admin, Invite(label='测试学生'))
    svc.register(reg(inv['code']))
    student = auth.authenticate('new_student', 'a memorable test phrase 2026')
    for actor in [admin, teacher, student]:
        headers = {'Authorization': 'Bearer ' + auth.issue_token(actor)}
        initial = client.get('/api/v1/accounts/avatar', headers=headers)
        assert initial.json() == {'image': None, 'revision': None}
        saved = client.put('/api/v1/accounts/avatar', headers=headers, json={'image': raster(), 'expected_revision': None})
        assert saved.status_code == 200 and saved.json()['image'].startswith('data:image/jpeg;base64,')
        # A new session/token sees the exact same persisted image.
        again = client.get('/api/v1/accounts/avatar', headers={'Authorization':'Bearer ' + auth.issue_token(actor)})
        assert again.json() == saved.json() and 'no-store' in again.headers['cache-control']
    with sessions() as s:
        assert len(s.scalars(select(UserAvatar)).all()) == 3
        assert 'base64' not in ''.join(str(row.detail) for row in s.scalars(select(AuditLog)))
    assert client.get('/api/v1/accounts/avatar').status_code == 401
    assert client.put('/api/v1/accounts/avatar', json={'image':raster(), 'expected_revision':None}).status_code == 401


def test_restore_and_stale_save_never_overwrites(setup):
    svc, sessions, admin, teacher, course, auth, client = setup
    first = svc.save_avatar(teacher, raster(), None)
    with pytest.raises(AvatarConflict): svc.save_avatar(teacher, raster('JPEG'), None)
    restored = svc.save_avatar(teacher, None, first['revision'])
    assert restored['image'] is None and restored['revision'] != first['revision']
    with pytest.raises(AvatarConflict): svc.save_avatar(teacher, raster(), first['revision'])
    headers = {'Authorization':'Bearer ' + auth.issue_token(teacher)}
    conflict = client.put('/api/v1/accounts/avatar', headers=headers, json={'image':raster(), 'expected_revision':first['revision']})
    assert conflict.status_code == 409
    assert svc.avatar(teacher) == restored
    invalid = client.put('/api/v1/accounts/avatar', headers=headers, json={'image':'data:image/svg+xml;base64,PHN2Zy8+', 'expected_revision':restored['revision']})
    assert invalid.status_code == 400 and svc.avatar(teacher) == restored


def test_cannot_target_other_users_or_use_revoked_session(setup):
    svc, sessions, admin, teacher, course, auth, client = setup
    headers = {'Authorization':'Bearer ' + auth.issue_token(teacher)}
    assert client.put('/api/v1/accounts/avatar', headers=headers, json={'image':raster(), 'expected_revision':None, 'user_id':admin.id}).status_code == 422
    assert client.put('/api/v1/accounts/avatar', headers=headers, json={'image':raster()}).status_code == 422
    assert client.get('/api/v1/accounts/avatar/' + admin.id, headers=headers).status_code == 404
    assert svc.avatar(admin)['image'] is None
    with sessions.begin() as s: s.get(User, UUID(teacher.id)).session_version += 1
    assert client.get('/api/v1/accounts/avatar', headers=headers).status_code == 401
    assert client.put('/api/v1/accounts/avatar', headers=headers, json={'image':raster(), 'expected_revision':None}).status_code == 401
    with pytest.raises(PermissionError): svc.save_avatar(teacher, raster(), None)


def test_rate_limit_and_invalid_upload_does_not_replace(setup):
    svc, sessions, admin, teacher, course, auth, client = setup
    headers = {'Authorization':'Bearer ' + auth.issue_token(teacher)}
    saved = svc.save_avatar(teacher, raster(), None)
    for _ in range(20):
        result = client.put('/api/v1/accounts/avatar', headers=headers, json={'image':'invalid', 'expected_revision':saved['revision']})
        assert result.status_code == 400
    assert client.put('/api/v1/accounts/avatar', headers=headers, json={'image':None, 'expected_revision':saved['revision']}).status_code == 429
    assert svc.avatar(teacher) == saved
