"""Tests for BitbucketDCPRsMixin."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from openhands.integrations.bitbucket_data_center.bitbucket_data_center_service import (
    BitbucketDataCenterService,
)
from openhands.integrations.service_types import ResourceNotFoundError


def make_service():
    return BitbucketDataCenterService(
        token=SecretStr('tok'), base_domain='host.example.com'
    )


# ── create_pr ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_pr_payload_structure():
    svc = make_service()
    mock_response = {
        'id': 1,
        'links': {'self': [{'href': 'https://host.example.com/pr/1'}]},
    }

    with patch.object(svc, '_make_request', return_value=(mock_response, {})) as mock_req:
        await svc.create_pr('PROJ/myrepo', 'feature', 'main', 'My PR')

    _, kwargs = mock_req.call_args
    payload = kwargs.get('params') or mock_req.call_args[1].get('params') or mock_req.call_args[0][1]
    assert payload['fromRef']['id'] == 'refs/heads/feature'
    assert payload['toRef']['id'] == 'refs/heads/main'
    assert payload['fromRef']['repository']['slug'] == 'myrepo'
    assert payload['fromRef']['repository']['project']['key'] == 'PROJ'


@pytest.mark.asyncio
async def test_create_pr_returns_href():
    svc = make_service()
    mock_response = {
        'id': 5,
        'links': {'self': [{'href': 'https://host.example.com/pr/5'}]},
    }

    with patch.object(svc, '_make_request', return_value=(mock_response, {})):
        url = await svc.create_pr('PROJ/myrepo', 'feature', 'main', 'My PR')

    assert url == 'https://host.example.com/pr/5'


@pytest.mark.asyncio
async def test_create_pr_no_link_returns_empty_string():
    svc = make_service()
    mock_response = {'id': 5, 'links': {}}

    with patch.object(svc, '_make_request', return_value=(mock_response, {})):
        url = await svc.create_pr('PROJ/myrepo', 'feature', 'main', 'My PR')

    assert url == ''


@pytest.mark.asyncio
async def test_create_pr_no_link_logs_debug(caplog):
    import logging

    from openhands.core.logger import openhands_logger

    svc = make_service()
    mock_response = {'id': 1, 'links': {}}

    # openhands_logger has propagate=False, so attach caplog's handler directly
    openhands_logger.addHandler(caplog.handler)
    try:
        with patch.object(svc, '_make_request', return_value=(mock_response, {})):
            with caplog.at_level(logging.DEBUG, logger='openhands'):
                url = await svc.create_pr('PROJ/myrepo', 'feature', 'main', 'My PR')
    finally:
        openhands_logger.removeHandler(caplog.handler)

    assert url == ''
    assert any('no self link' in r.message for r in caplog.records)


# ── get_pr_details ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pr_details_returns_raw_data():
    svc = make_service()
    mock_data = {'id': 3, 'state': 'OPEN', 'title': 'A PR'}

    with patch.object(svc, '_make_request', return_value=(mock_data, {})):
        result = await svc.get_pr_details('PROJ/myrepo', 3)

    assert result == mock_data


# ── is_pr_open ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_is_pr_open_returns_true():
    svc = make_service()

    with patch.object(
        svc, 'get_pr_details', new=AsyncMock(return_value={'state': 'OPEN'})
    ):
        assert await svc.is_pr_open('PROJ/myrepo', 1) is True


@pytest.mark.asyncio
async def test_is_pr_open_returns_false_for_merged():
    svc = make_service()

    with patch.object(
        svc, 'get_pr_details', new=AsyncMock(return_value={'state': 'MERGED'})
    ):
        assert await svc.is_pr_open('PROJ/myrepo', 1) is False


@pytest.mark.asyncio
async def test_is_pr_open_returns_false_for_declined():
    svc = make_service()

    with patch.object(
        svc, 'get_pr_details', new=AsyncMock(return_value={'state': 'DECLINED'})
    ):
        assert await svc.is_pr_open('PROJ/myrepo', 1) is False


@pytest.mark.asyncio
async def test_is_pr_open_propagates_resource_not_found():
    svc = make_service()

    with patch.object(
        svc,
        'get_pr_details',
        new=AsyncMock(side_effect=ResourceNotFoundError('PR not found')),
    ):
        with pytest.raises(ResourceNotFoundError):
            await svc.is_pr_open('PROJ/myrepo', 999)
