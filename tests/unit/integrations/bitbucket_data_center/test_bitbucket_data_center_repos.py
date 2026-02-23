"""Tests for BitbucketDCReposMixin."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from openhands.integrations.bitbucket_data_center.bitbucket_data_center_service import (
    BitbucketDataCenterService,
)
from openhands.server.types import AppMode


def make_service():
    return BitbucketDataCenterService(
        token=SecretStr('tok'), base_domain='host.example.com'
    )


def _repo_dict(key='PROJ', slug='myrepo'):
    return {'id': 1, 'slug': slug, 'project': {'key': key}, 'public': False}


# ── get_paginated_repos ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_paginated_repos_parses_values():
    svc = make_service()
    mock_response = {
        'values': [_repo_dict()],
        'isLastPage': True,
    }
    with patch.object(svc, '_make_request', return_value=(mock_response, {})):
        repos = await svc.get_paginated_repos(1, 25, 'name', 'PROJ')

    assert len(repos) == 1
    assert repos[0].full_name == 'PROJ/myrepo'
    assert repos[0].link_header == ''


@pytest.mark.asyncio
async def test_get_paginated_repos_has_next_page():
    svc = make_service()
    mock_response = {
        'values': [_repo_dict()],
        'isLastPage': False,
        'nextPageStart': 25,
    }
    with patch.object(svc, '_make_request', return_value=(mock_response, {})):
        repos = await svc.get_paginated_repos(1, 25, 'name', 'PROJ')

    assert len(repos) == 1
    assert 'rel="next"' in repos[0].link_header


# ── get_all_repositories ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_all_repositories_iterates_projects():
    svc = make_service()

    async def fake_fetch(url, params, max_items):
        if '/projects' in url and '/repos' not in url:
            return [{'key': 'PROJ1'}, {'key': 'PROJ2'}]
        if 'PROJ1' in url:
            return [_repo_dict('PROJ1', 'repo1')]
        if 'PROJ2' in url:
            return [_repo_dict('PROJ2', 'repo2')]
        return []

    with patch.object(svc, '_fetch_paginated_data', side_effect=fake_fetch):
        repos = await svc.get_all_repositories('name', AppMode.SAAS)

    full_names = {r.full_name for r in repos}
    assert 'PROJ1/repo1' in full_names
    assert 'PROJ2/repo2' in full_names


# ── search_repositories ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_repositories_projects_url():
    svc = make_service()
    query = 'https://host.example.com/projects/PROJ/repos/myrepo'

    mock_repo = _repo_dict('PROJ', 'myrepo')
    with patch.object(
        svc,
        'get_repository_details_from_repo_name',
        new=AsyncMock(return_value=svc._parse_repository(mock_repo)),
    ) as mock_detail:
        repos = await svc.search_repositories(query, 25, 'name', 'asc', True, AppMode.SAAS)

    mock_detail.assert_called_once_with('PROJ/myrepo')
    assert len(repos) == 1


@pytest.mark.asyncio
async def test_search_repositories_scm_url():
    svc = make_service()
    query = 'https://host.example.com/scm/proj/myrepo.git'

    mock_repo = _repo_dict('PROJ', 'myrepo')
    with patch.object(
        svc,
        'get_repository_details_from_repo_name',
        new=AsyncMock(return_value=svc._parse_repository(mock_repo)),
    ) as mock_detail:
        repos = await svc.search_repositories(query, 25, 'name', 'asc', True, AppMode.SAAS)

    # project key is uppercased from 'proj' → 'PROJ'
    mock_detail.assert_called_once_with('PROJ/myrepo')
    assert len(repos) == 1


@pytest.mark.asyncio
async def test_search_repositories_slash_query():
    svc = make_service()
    query = 'PROJ/myrepo'

    with patch.object(
        svc,
        'get_paginated_repos',
        new=AsyncMock(return_value=[svc._parse_repository(_repo_dict())]),
    ) as mock_paged:
        repos = await svc.search_repositories(query, 25, 'name', 'asc', False, AppMode.SAAS)

    mock_paged.assert_called_once_with(1, 25, 'name', 'PROJ', 'myrepo')
    assert len(repos) == 1


@pytest.mark.asyncio
async def test_search_repositories_plain_text():
    svc = make_service()
    mock_response = {'values': [_repo_dict()]}

    with patch.object(svc, '_make_request', return_value=(mock_response, {})) as mock_req:
        repos = await svc.search_repositories('myrepo', 25, 'name', 'asc', False, AppMode.SAAS)

    call_url = mock_req.call_args[0][0]
    call_params = mock_req.call_args[0][1]
    assert call_url.endswith('/repos')
    assert call_params['name'] == 'myrepo'
    assert len(repos) == 1


# ── get_installations ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_installations_returns_project_keys():
    svc = make_service()

    async def fake_fetch(url, params, max_items):
        return [{'key': 'PROJ1'}, {'key': 'PROJ2'}, {'name': 'no-key'}]

    with patch.object(svc, '_fetch_paginated_data', side_effect=fake_fetch):
        keys = await svc.get_installations()

    assert keys == ['PROJ1', 'PROJ2']
