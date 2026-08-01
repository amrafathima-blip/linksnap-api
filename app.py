import string
import random
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from flask import Flask, request, jsonify, redirect, abort
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///linksnap.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class Link(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    short_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    original_url = db.Column(db.Text, nullable=False)
    clicks = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=True)

    def is_expired(self):
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=timezone.utc)

    def to_dict(self, base_url):
        return {
            "short_code": self.short_code,
            "short_url": f"{base_url.rstrip('/')}/{self.short_code}",
            "original_url": self.original_url,
            "clicks": self.clicks,
            "created_at": self.created_at.isoformat() + "Z",
            "expires_at": self.expires_at.isoformat() + "Z" if self.expires_at else None
        }

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
def is_valid_url(url: str) -> bool:
    """Validates URL structure and scheme."""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except Exception:
        return False

def generate_random_code(length=6) -> str:
    """Generates a random alphanumeric code."""
    chars = string.ascii_letters + string.digits
    while True:
        code = ''.join(random.choices(chars, k=length))
        if not Link.query.filter_by(short_code=code).first():
            return code

# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------
@app.route('/api/v1/shorten', methods=['POST'])
def shorten_url():
    data = request.get_json() or {}
    original_url = data.get('original_url')
    custom_code = data.get('custom_code')
    expires_in_days = data.get('expires_in_days')

    # Validate URL
    if not original_url or not is_valid_url(original_url):
        return jsonify({"error": "Invalid URL format"}), 400

    # Custom code logic
    if custom_code:
        if Link.query.filter_by(short_code=custom_code).first():
            return jsonify({"error": "Custom code already taken"}), 409
        short_code = custom_code
    else:
        short_code = generate_random_code()

    # Calculate expiration
    expires_at = None
    if expires_in_days is not None:
        try:
            days = int(expires_in_days)
            if days <= 0:
                return jsonify({"error": "expires_in_days must be a positive integer"}), 400
            expires_at = datetime.now(timezone.utc) + timedelta(days=days)
        except ValueError:
            return jsonify({"error": "expires_in_days must be an integer"}), 400

    # Create & Save
    link = Link(
        short_code=short_code,
        original_url=original_url,
        expires_at=expires_at
    )
    db.session.add(link)
    db.session.commit()

    return jsonify(link.to_dict(request.host_url)), 201


@app.route('/<short_code>', methods=['GET'])
def redirect_to_url(short_code):
    link = Link.query.filter_by(short_code=short_code).first()

    if not link:
        return jsonify({"error": "Short link not found"}), 404

    if link.is_expired():
        return jsonify({"error": "This short link has expired"}), 410

    # Increment click count & redirect
    link.clicks += 1
    db.session.commit()

    return redirect(link.original_url, code=302)


@app.route('/api/v1/links/<short_code>', methods=['GET'])
def get_link_stats(short_code):
    link = Link.query.filter_by(short_code=short_code).first()

    if not link:
        return jsonify({"error": "Short link not found"}), 404

    return jsonify(link.to_dict(request.host_url)), 200


@app.route('/api/v1/links/<short_code>', methods=['DELETE'])
def delete_link(short_code):
    link = Link.query.filter_by(short_code=short_code).first()

    if not link:
        return jsonify({"error": "Short link not found"}), 404

    db.session.delete(link)
    db.session.commit()

    return '', 204

# -----------------------------------------------------------------------------
# Application Setup
# -----------------------------------------------------------------------------
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)