import pytest
from datetime import datetime, timezone, timedelta
from app import app, db, Link

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client
        with app.app_context():
            db.drop_all()

def test_create_short_link_success(client):
    payload = {"original_url": "https://example.com/long/path"}
    response = client.post('/api/v1/shorten', json=payload)
    
    assert response.status_code == 201
    data = response.get_json()
    assert "short_code" in data
    assert data["original_url"] == payload["original_url"]
    assert len(data["short_code"]) == 6

def test_create_short_link_custom_code(client):
    payload = {
        "original_url": "https://example.com",
        "custom_code": "my-custom-code"
    }
    response = client.post('/api/v1/shorten', json=payload)
    assert response.status_code == 201
    assert response.get_json()["short_code"] == "my-custom-code"

    # Test conflict on duplicate custom code
    response_conflict = client.post('/api/v1/shorten', json=payload)
    assert response_conflict.status_code == 409

def test_invalid_url(client):
    response = client.post('/api/v1/shorten', json={"original_url": "not-a-valid-url"})
    assert response.status_code == 400

def test_redirect_and_increment_clicks(client):
    # 1. Create Link
    res = client.post('/api/v1/shorten', json={"original_url": "https://example.com"})
    code = res.get_json()["short_code"]

    # 2. Access Redirect
    redirect_res = client.get(f'/{code}')
    assert redirect_res.status_code == 302
    assert redirect_res.headers['Location'] == 'https://example.com'

    # 3. Check Analytics
    stats_res = client.get(f'/api/v1/links/{code}')
    assert stats_res.status_code == 200
    assert stats_res.get_json()["clicks"] == 1

def test_expiration(client):
    # Create expired link directly in DB
    with app.app_context():
        expired_link = Link(
            short_code="expired",
            original_url="https://example.com",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1)
        )
        db.session.add(expired_link)
        db.session.commit()

    response = client.get('/expired')
    assert response.status_code == 410

def test_delete_link(client):
    res = client.post('/api/v1/shorten', json={"original_url": "https://example.com"})
    code = res.get_json()["short_code"]

    del_res = client.delete(f'/api/v1/links/{code}')
    assert del_res.status_code == 204

    get_res = client.get(f'/api/v1/links/{code}')
    assert get_res.status_code == 404