"""Public transport contract; runtime TLS is additionally exercised in Docker."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_public_tls_overlay_uses_readonly_certificates_and_https_health():
    overlay = (ROOT / "infra/docker-compose.public-tls.yml").read_text()
    assert "wayfinding-external-tls.nginx.conf:/etc/nginx/nginx.conf:ro" in overlay
    assert "${WAYFINDING_TLS_CERT_DIR:?" in overlay
    assert "target: /etc/nginx/certs" in overlay
    assert "read_only: true" in overlay
    assert "create_host_path: false" in overlay
    assert "https://sfuai.ca:8007/demo/v1/health" in overlay
    assert "--no-check-certificate" not in overlay


def test_public_tls_preserves_identity_and_redirects_to_fixed_public_origin():
    proxy = (ROOT / "infra/wayfinding-external-tls.nginx.conf").read_text()
    assert "listen 8007 ssl" in proxy
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in proxy
    assert "ssl_certificate /etc/nginx/certs/fullchain.pem;" in proxy
    assert "ssl_certificate_key /etc/nginx/certs/privkey.pem;" in proxy
    assert "return 444;" in proxy
    assert "proxy_set_header Host demo;" in proxy
    assert "proxy_set_header X-Forwarded-For \"\";" in proxy
    assert "error_page 497 =307 https://sfuai.ca:8017$request_uri;" in proxy
