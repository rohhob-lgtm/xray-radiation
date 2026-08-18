"""GitHubConnector — real GitHub REST API over ApiKeyAuthStrategy (user-supplied PAT)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ...base import PlatformConnector, ConnectorActionResult, HealthStatus
from ...manifest import ConnectorManifest, ConnectorCategory, AuthStrategyType, CapabilityDefinition
from ...auth_strategies.api_key import ApiKeyAuthStrategy, ApiKeyConfig
from . import client as github_client

GITHUB_MANIFEST = ConnectorManifest(
    provider="github", display_name="GitHub", icon="🐙",
    category=ConnectorCategory.CODE_REPO, auth_strategy_type=AuthStrategyType.API_KEY,
    supports_sync=False, supports_health_check=True,
    capabilities=(
        CapabilityDefinition("github.list_repos", "List the user's repositories"),
        CapabilityDefinition("github.read_file", "Read a file from a repo",
                              parameters_schema={"owner": {"type": "string", "required": True},
                                                  "repo": {"type": "string", "required": True},
                                                  "path": {"type": "string", "required": True}}),
        CapabilityDefinition("github.list_issues", "List issues in a repo",
                              parameters_schema={"owner": {"type": "string", "required": True},
                                                  "repo": {"type": "string", "required": True}}),
        CapabilityDefinition("github.create_pr", "Open a pull request", is_destructive=True,
                              parameters_schema={"owner": {"type": "string", "required": True},
                                                  "repo": {"type": "string", "required": True},
                                                  "title": {"type": "string", "required": True},
                                                  "head": {"type": "string", "required": True},
                                                  "base": {"type": "string", "required": True}}),
    ),
)


class GitHubConnector(PlatformConnector):
    manifest = GITHUB_MANIFEST

    def __init__(self):
        self.auth_strategy = ApiKeyAuthStrategy(ApiKeyConfig(field_label="Personal Access Token"))

    async def execute_action(self, db: Session, user_id: str, action: str, parameters: dict[str, Any]) -> ConnectorActionResult:
        token = await self._get_bearer_token(db, user_id)
        if not token:
            return ConnectorActionResult(success=False, action=action, error_code="NOT_CONNECTED")

        try:
            if action == "github.list_repos":
                data = {"repos": await github_client.list_repos(token)}
            elif action == "github.read_file":
                owner, repo, path = parameters.get("owner"), parameters.get("repo"), parameters.get("path")
                if not owner or not repo or not path:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                data = await github_client.read_file(token, owner, repo, path)
            elif action == "github.list_issues":
                owner, repo = parameters.get("owner"), parameters.get("repo")
                if not owner or not repo:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                data = {"issues": await github_client.list_issues(token, owner, repo)}
            elif action == "github.create_pr":
                owner, repo = parameters.get("owner"), parameters.get("repo")
                title, head, base = parameters.get("title"), parameters.get("head"), parameters.get("base")
                if not all([owner, repo, title, head, base]):
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                data = await github_client.create_pull_request(token, owner, repo, title, head, base, parameters.get("body", ""))
            else:
                return ConnectorActionResult(success=False, action=action, error_code="NOT_IMPLEMENTED")
        except github_client.GitHubApiError as exc:
            return ConnectorActionResult(success=False, action=action,
                                          error_code=f"GITHUB_API_ERROR_{exc.status_code}", error_message=str(exc))

        await self._mark_action_success(db, user_id)
        return ConnectorActionResult(success=True, action=action, data=data)

    async def health_check(self, db: Session, user_id: str) -> HealthStatus:
        token = await self._get_bearer_token(db, user_id)
        if not token:
            return HealthStatus(healthy=False, detail="Not connected")
        try:
            await github_client.get_authenticated_user(token)
            return HealthStatus(healthy=True)
        except github_client.GitHubApiError as exc:
            return HealthStatus(healthy=False, detail=str(exc))


github_connector = GitHubConnector()
