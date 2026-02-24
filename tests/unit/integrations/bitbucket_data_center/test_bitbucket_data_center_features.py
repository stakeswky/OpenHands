"""Tests for BitbucketDCFeaturesMixin (get_microagent_content, _process_microagents_directory)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from openhands.integrations.bitbucket_data_center.bitbucket_data_center_service import (
    BitbucketDataCenterService,
)
from openhands.integrations.service_types import (
    AuthenticationError,
    OwnerType,
    ProviderType,
    Repository,
    ResourceNotFoundError,
)
from openhands.microagent.types import MicroagentContentResponse


def make_service():
    return BitbucketDataCenterService(
        token=SecretStr('tok'), base_domain='host.example.com'
    )


def make_repo(main_branch='main'):
    return Repository(
        id='1',
        full_name='PROJ/repo',
        git_provider=ProviderType.BITBUCKET_DATA_CENTER,
        is_public=False,
        stargazers_count=None,
        pushed_at=None,
        owner_type=OwnerType.ORGANIZATION,
        link_header=None,
        main_branch=main_branch,
    )


def make_file_item(name, item_type='FILE'):
    """Build a DC browse directory item dict."""
    return {
        'type': item_type,
        'path': {
            'name': name,
            'toString': f'.openhands/microagents/{name}',
        },
    }


# ── get_microagent_content ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_microagent_content_assembles_lines():
    svc = make_service()
    lines_response = {'lines': [{'text': 'line1'}, {'text': 'line2'}]}
    dummy_result = MicroagentContentResponse(content='line1\nline2', path='file.md')

    with patch.object(
        svc,
        'get_repository_details_from_repo_name',
        new=AsyncMock(return_value=make_repo()),
    ):
        with patch.object(
            svc, '_make_request', new=AsyncMock(return_value=(lines_response, {}))
        ):
            with patch.object(
                svc, '_parse_microagent_content', return_value=dummy_result
            ) as mock_parse:
                result = await svc.get_microagent_content('PROJ/repo', 'file.md')

    mock_parse.assert_called_once_with('line1\nline2', 'file.md')
    assert result is dummy_result


@pytest.mark.asyncio
async def test_get_microagent_content_no_main_branch_raises():
    svc = make_service()

    with patch.object(
        svc,
        'get_repository_details_from_repo_name',
        new=AsyncMock(return_value=make_repo(main_branch=None)),
    ):
        with pytest.raises(ResourceNotFoundError):
            await svc.get_microagent_content('PROJ/repo', 'file.md')


@pytest.mark.asyncio
async def test_get_microagent_content_not_found_propagates():
    svc = make_service()

    with patch.object(
        svc,
        'get_repository_details_from_repo_name',
        new=AsyncMock(return_value=make_repo()),
    ):
        with patch.object(
            svc,
            '_make_request',
            new=AsyncMock(side_effect=ResourceNotFoundError('not found')),
        ):
            with pytest.raises(ResourceNotFoundError):
                await svc.get_microagent_content('PROJ/repo', 'file.md')


# ── _process_microagents_directory ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_microagents_directory_404_returns_empty():
    svc = make_service()

    with patch.object(
        svc,
        'get_repository_details_from_repo_name',
        new=AsyncMock(return_value=make_repo()),
    ):
        with patch.object(
            svc,
            '_make_request',
            new=AsyncMock(side_effect=ResourceNotFoundError('directory not found')),
        ):
            result = await svc._process_microagents_directory(
                'PROJ/repo', '.openhands/microagents'
            )

    assert result == []


@pytest.mark.asyncio
async def test_process_microagents_directory_non_404_propagates():
    svc = make_service()

    with patch.object(
        svc,
        'get_repository_details_from_repo_name',
        new=AsyncMock(return_value=make_repo()),
    ):
        with patch.object(
            svc,
            '_make_request',
            new=AsyncMock(side_effect=AuthenticationError('auth failed')),
        ):
            with pytest.raises(AuthenticationError):
                await svc._process_microagents_directory(
                    'PROJ/repo', '.openhands/microagents'
                )


@pytest.mark.asyncio
async def test_process_microagents_directory_returns_md_files_only():
    svc = make_service()

    # One valid .md, one .py (excluded), one README.md (excluded), one directory (excluded)
    response = {
        'children': {
            'values': [
                make_file_item('agent.md'),
                make_file_item('script.py'),
                make_file_item('README.md'),
                make_file_item('subdir', item_type='DIRECTORY'),
            ],
            'isLastPage': True,
        }
    }

    with patch.object(
        svc,
        'get_repository_details_from_repo_name',
        new=AsyncMock(return_value=make_repo()),
    ):
        with patch.object(
            svc, '_make_request', new=AsyncMock(return_value=(response, {}))
        ):
            result = await svc._process_microagents_directory(
                'PROJ/repo', '.openhands/microagents'
            )

    assert len(result) == 1
    assert result[0].name == 'agent'


@pytest.mark.asyncio
async def test_process_microagents_directory_pagination():
    svc = make_service()

    page1 = {
        'children': {
            'values': [make_file_item('first.md')],
            'isLastPage': False,
            'nextPageStart': 25,
        }
    }
    page2 = {
        'children': {
            'values': [make_file_item('second.md')],
            'isLastPage': True,
        }
    }

    mock_make_request = AsyncMock(side_effect=[(page1, {}), (page2, {})])

    with patch.object(
        svc,
        'get_repository_details_from_repo_name',
        new=AsyncMock(return_value=make_repo()),
    ):
        with patch.object(svc, '_make_request', mock_make_request):
            result = await svc._process_microagents_directory(
                'PROJ/repo', '.openhands/microagents'
            )

    assert mock_make_request.call_count == 2
    assert len(result) == 2
    names = {r.name for r in result}
    assert names == {'first', 'second'}
