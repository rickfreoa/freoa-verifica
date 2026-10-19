"""Detecção de desafios WAF/CAPTCHA."""

from __future__ import annotations

from freoa_verifica.connectors.challenge import detect_challenge
from freoa_verifica.transport import ChallengeDetected
from tests.fixture_util import load_fixture


def test_detect_body_markers():
    body = load_fixture("challenge_aws_waf_sample")
    found = detect_challenge(status=200, body=body)
    assert isinstance(found, ChallengeDetected)
    assert found.args[0] in {"f5", "tspd", "bobcmn", "captcha"}


def test_detect_202_empty():
    found = detect_challenge(status=202, body=b"", headers={"x-amzn-waf-action": "challenge"})
    assert found is not None
    assert found.args[0] == "aws_waf"


def test_detect_403_html():
    # 0045: 403 sem marcador é recusa identificada, não desafio; com marcador segue desafio.
    assert detect_challenge(
        status=403,
        body=b"<html><body>blocked</body></html>",
        headers={"content-type": "text/html"},
    ) is None
    found = detect_challenge(
        status=403,
        body=b"<html><body>AwsWafIntegration.getToken()</body></html>",
        headers={"content-type": "text/html"},
    )
    assert found is not None and found.args[0] == "aws_waf"


def test_clean_body_no_challenge():
    assert detect_challenge(status=200, body=b'{"TotalRows":1}') is None
