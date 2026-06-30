import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module

@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as client:
        yield client

def test_upload_no_file_provided(client):
    response = client.post('/upload')
    assert response.status_code == 400
    assert 'error' in response.get_json()

@patch('app.get_db_connection')
@patch('app.s3')
def test_upload_success(mock_s3, mock_get_db_connection, client):
    mock_s3.upload_fileobj.return_value = None

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_db_connection.return_value = mock_conn

    data = {'file': (open(__file__, 'rb'), 'test_file.py')}
    response = client.post('/upload', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    assert 'uploaded successfully' in response.get_json()['message']

@patch('app.s3')
def test_download_generates_url(mock_s3, client):
    mock_s3.generate_presigned_url.return_value = 'https://fake-url.com/test.txt'
    response = client.get('/download/test.txt')
    assert response.status_code == 200
    assert response.get_json()['download_url'] == 'https://fake-url.com/test.txt'