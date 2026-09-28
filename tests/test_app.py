import pytest
import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module
import psycopg2.errors
from werkzeug.security import generate_password_hash


@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as client:
        yield client


def auth_header(user_id=1, username='testuser'):
    """
    Builds a real, valid JWT using the exact same secret and algorithm the
    app itself uses (read straight from app_module, not hardcoded here), so
    app.py's own jwt.decode() call will accept it just like a real login would.
    """
    token = app_module.jwt.encode(
        {
            'user_id': user_id,
            'username': username,
            'exp': datetime.now(timezone.utc) + timedelta(hours=1),
        },
        app_module.JWT_SECRET_KEY,
        algorithm=app_module.JWT_ALGORITHM,
    )
    return {'Authorization': f'Bearer {token}'}


# ---------- /register ----------

@patch('app.get_db_connection')
def test_register_success(mock_get_db_connection, client):
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)  # the new user's id, from RETURNING id
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db_connection.return_value = mock_conn

    response = client.post('/register', json={'username': 'alice', 'password': 'pass123'})
    assert response.status_code == 201
    assert response.get_json()['user_id'] == 1

def test_register_missing_fields(client):
    response = client.post('/register', json={'username': 'alice'})  # no password
    assert response.status_code == 400

@patch('app.get_db_connection')
def test_register_duplicate_username(mock_get_db_connection, client):
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = psycopg2.errors.UniqueViolation()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db_connection.return_value = mock_conn

    response = client.post('/register', json={'username': 'alice', 'password': 'pass123'})
    assert response.status_code == 409


# ---------- /login ----------

@patch('app.get_db_connection')
def test_login_success(mock_get_db_connection, client):
    real_hash = generate_password_hash('correct-password')
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1, real_hash)  # (id, password_hash) from the SELECT
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db_connection.return_value = mock_conn

    response = client.post('/login', json={'username': 'alice', 'password': 'correct-password'})
    assert response.status_code == 200
    assert 'token' in response.get_json()

@patch('app.get_db_connection')
def test_login_wrong_password(mock_get_db_connection, client):
    real_hash = generate_password_hash('correct-password')
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1, real_hash)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db_connection.return_value = mock_conn

    response = client.post('/login', json={'username': 'alice', 'password': 'wrong-password'})
    assert response.status_code == 401

@patch('app.get_db_connection')
def test_login_nonexistent_user(mock_get_db_connection, client):
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # no such username
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db_connection.return_value = mock_conn

    response = client.post('/login', json={'username': 'ghost', 'password': 'whatever'})
    assert response.status_code == 401


# ---------- /upload ----------

def test_upload_requires_auth(client):
    response = client.post('/upload')
    assert response.status_code == 401

def test_upload_no_file_provided(client):
    response = client.post('/upload', headers=auth_header())
    assert response.status_code == 400
    assert 'error' in response.get_json()

@patch('app.get_db_connection')
@patch('app.s3')
def test_upload_success(mock_s3, mock_get_db_connection, client):
    mock_s3.upload_fileobj.return_value = None

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (42,)  # the new file's id, from RETURNING id
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db_connection.return_value = mock_conn

    data = {'file': (open(__file__, 'rb'), 'test_file.py')}
    response = client.post(
        '/upload', data=data, content_type='multipart/form-data', headers=auth_header()
    )
    assert response.status_code == 200
    assert 'uploaded successfully' in response.get_json()['message']


# ---------- /download/<filename> ----------

def test_download_requires_auth(client):
    response = client.get('/download/test.txt')
    assert response.status_code == 401

@patch('app.get_db_connection')
def test_download_file_not_found(mock_get_db_connection, client):
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # no such file in file_uploads
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db_connection.return_value = mock_conn

    response = client.get('/download/nope.txt', headers=auth_header())
    assert response.status_code == 404

@patch('app.get_db_connection')
def test_download_permission_denied(mock_get_db_connection, client):
    mock_cursor = MagicMock()
    # First call (file lookup) finds the file; second call (permission check) finds nothing.
    mock_cursor.fetchone.side_effect = [(1,), None]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db_connection.return_value = mock_conn

    response = client.get('/download/private.txt', headers=auth_header(user_id=99))
    assert response.status_code == 403

@patch('app.get_db_connection')
@patch('app.s3')
def test_download_generates_url(mock_s3, mock_get_db_connection, client):
    mock_s3.generate_presigned_url.return_value = 'https://fake-url.com/test.txt'
    mock_cursor = MagicMock()
    # First call (file lookup) finds the file; second call (permission check) finds a grant.
    mock_cursor.fetchone.side_effect = [(1,), (1,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db_connection.return_value = mock_conn

    response = client.get('/download/test.txt', headers=auth_header(user_id=1))
    assert response.status_code == 200
    assert response.get_json()['download_url'] == 'https://fake-url.com/test.txt'


# ---------- /files/<filename>/share ----------

def test_share_requires_auth(client):
    response = client.post('/files/test.txt/share', json={'username': 'bob'})
    assert response.status_code == 401

@patch('app.get_db_connection')
def test_share_not_owner(mock_get_db_connection, client):
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1, 55)  # (file_id, owner_id) -- owner is user 55
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db_connection.return_value = mock_conn

    response = client.post(
        '/files/test.txt/share', json={'username': 'bob'}, headers=auth_header(user_id=1)
    )
    assert response.status_code == 403

@patch('app.get_db_connection')
def test_share_target_user_not_found(mock_get_db_connection, client):
    mock_cursor = MagicMock()
    # First call (file lookup): caller (user_id=1) IS the owner. Second call (user lookup): no such user.
    mock_cursor.fetchone.side_effect = [(1, 1), None]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db_connection.return_value = mock_conn

    response = client.post(
        '/files/test.txt/share', json={'username': 'ghost'}, headers=auth_header(user_id=1)
    )
    assert response.status_code == 404

@patch('app.get_db_connection')
def test_share_success(mock_get_db_connection, client):
    mock_cursor = MagicMock()
    # File lookup: caller owns it. User lookup: target user exists with id=2.
    mock_cursor.fetchone.side_effect = [(1, 1), (2,)]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db_connection.return_value = mock_conn

    response = client.post(
        '/files/test.txt/share', json={'username': 'bob'}, headers=auth_header(user_id=1)
    )
    assert response.status_code == 200
    assert 'shared with bob' in response.get_json()['message']
