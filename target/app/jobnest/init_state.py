"""시연 상태 만들기: DNS 영역 파일과 TLS 인증서.

`docker compose up` 때 init 서비스가 한 번 실행한다. 결과는 공유 볼륨 /state에 쓴다.
- /state/dns/*.db   CoreDNS가 읽는 영역 파일 (#1, #4, #6, #32, FR-01 소유권 TXT)
- /state/tls/       nginx가 쓰는 서버 인증서와 시연용 CA (#28)

CA는 처음 한 번만 만들고 계속 쓴다. 점검 엔진이 CA를 믿게 설정하면 FIX_28=1 상태의
인증서가 "정상"으로 보이고, FIX_28=0 상태의 자체 서명 인증서는 오류로 보인다.
"""

import datetime as dt
import ipaddress
import os
import time
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from . import config as c

STATE = Path(os.environ.get("STATE_DIR", "/state"))
PROXY_IP = os.environ.get("PROXY_IP", "10.253.53.80")
VERIFY_NAME = os.environ.get("A2D_VERIFY_NAME", "_a2d-verify").strip().strip(".")
VERIFY_VALUE = os.environ.get("A2D_VERIFY_VALUE", "").strip()


def zone(origin: str, records: list[str], serial: int) -> str:
    head = f"""$ORIGIN {origin}.
$TTL 60
@ IN SOA ns1.{origin}. hostmaster.{origin}. {serial} 60 60 86400 60
@ IN NS ns1.{origin}.
ns1 IN A {PROXY_IP}
"""
    return head + "\n".join(records) + "\n"


def write_zones() -> None:
    serial = int(time.time())  # CoreDNS는 serial이 커지면 영역 파일을 다시 읽는다.
    d = c.DOMAIN
    rec = [
        f"@ IN A {PROXY_IP}",
        f"www IN A {PROXY_IP}",
        f"api IN A {PROXY_IP}",
        f"admin IN A {PROXY_IP}",
        f"staging IN A {PROXY_IP}",
        f"dev IN A {PROXY_IP}",
        f"mail IN A {PROXY_IP}",
        f"@ IN MX 10 mail.{d}.",
        # #4 위탁 서비스 연결
        f"recruit IN CNAME {c.EXT_BOOKING}.",
    ]
    # 감시 시연: 새로 열린 테스트 서버
    if c.test_server():
        rec.append(f"test IN A {PROXY_IP}")
    # #6 하위 도메인 탈취 가능성: 해지된 GitHub Pages를 가리키는 CNAME. 고치면 레코드를 지운다.
    if not c.fixed(6):
        rec.append(f"promo IN CNAME {c.EXT_PAGES}.")
    # #32 메일 사칭 방지
    if c.fixed(32):
        rec.append('@ IN TXT "v=spf1 include:_spf.google.com -all"')
        rec.append(f'_dmarc IN TXT "v=DMARC1; p=reject; rua=mailto:dmarc@{d}"')
    else:
        rec.append('@ IN TXT "v=spf1 +all"')
    # FR-01 소유권 확인. 이름 규칙은 apps/api와 맞춘다.
    if VERIFY_VALUE:
        rec.append(f'{VERIFY_NAME} IN TXT "{VERIFY_VALUE}"')

    dns = STATE / "dns"
    dns.mkdir(parents=True, exist_ok=True)
    (dns / "main.db").write_text(zone(d, rec, serial))
    # 우리 DNS가 가리키는 외부 이름. 시연 DNS가 이 이름들만 프록시로 돌려준다.
    (dns / "booking.db").write_text(zone(c.EXT_BOOKING, [f"@ IN A {PROXY_IP}"], serial))
    (dns / "pages.db").write_text(zone(c.EXT_PAGES, [f"@ IN A {PROXY_IP}"], serial))
    (dns / "bucket.db").write_text(zone(c.EXT_BUCKET, [f"@ IN A {PROXY_IP}"], serial))


def _key():
    return ec.generate_private_key(ec.SECP256R1())


def _pem_key(key) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _load_or_make_ca(tls: Path):
    ca_crt, ca_key = tls / "ca.crt", tls / "ca.key"
    if ca_crt.exists() and ca_key.exists():
        return (x509.load_pem_x509_certificate(ca_crt.read_bytes()),
                serialization.load_pem_private_key(ca_key.read_bytes(), None))
    key = _key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "A2D Demo Root CA"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "A2D Demo")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
        .sign(key, hashes.SHA256())
    )
    ca_key.write_bytes(_pem_key(key))
    ca_crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert, key


def write_certs() -> None:
    tls = STATE / "tls"
    tls.mkdir(parents=True, exist_ok=True)
    ca_cert, ca_key = _load_or_make_ca(tls)
    key = _key()
    now = dt.datetime.now(dt.timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, c.DOMAIN),
                         x509.NameAttribute(NameOID.ORGANIZATION_NAME, "JobNest")])
    sans = [x509.DNSName(h) for h in c.ALL_HOSTS] + [x509.IPAddress(ipaddress.ip_address(PROXY_IP))]
    builder = (
        x509.CertificateBuilder().subject_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    )
    if c.fixed(28):
        # 고친 상태: 시연 CA가 발급, 1년 유효.
        cert = (builder.issuer_name(ca_cert.subject)
                .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=365))
                .sign(ca_key, hashes.SHA256()))
        chain = cert.public_bytes(serialization.Encoding.PEM) + ca_cert.public_bytes(serialization.Encoding.PEM)
    else:
        # 결함 상태: 자체 서명이고 7일 뒤 만료.
        cert = (builder.issuer_name(subject)
                .not_valid_before(now - dt.timedelta(days=358)).not_valid_after(now + dt.timedelta(days=7))
                .sign(key, hashes.SHA256()))
        chain = cert.public_bytes(serialization.Encoding.PEM)
    (tls / "server.key").write_bytes(_pem_key(key))
    (tls / "server.crt").write_bytes(chain)
    for p in tls.iterdir():
        p.chmod(0o644)  # nginx 작업자가 읽도록. 시연용 키다.


def main() -> None:
    write_zones()
    write_certs()
    on = [n for n in c.FAULTS if c.fixed(n)]
    print(f"[init] domain={c.DOMAIN} proxy={PROXY_IP} fixed={on or '없음'}")


if __name__ == "__main__":
    main()
