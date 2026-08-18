"""
Manifest-only registrations for providers on the roadmap but not yet
implemented. Each manifest declares its real intended category, auth
strategy, and capability surface (all capabilities marked
is_implemented=False) so the framework can honestly describe "this is what
Connectors will support" without a single line of them claiming to work.
Enabling one for real later is: implement a PlatformConnector + compose the
already-existing matching AuthStrategy — no framework changes.
"""
from __future__ import annotations

from ..manifest import ConnectorManifest, ConnectorCategory, AuthStrategyType, CapabilityDefinition


def _cap(action: str, description: str, scopes: tuple[str, ...] = ()) -> CapabilityDefinition:
    return CapabilityDefinition(action, description, required_scopes=scopes, is_implemented=False)


PLACEHOLDER_MANIFESTS: list[ConnectorManifest] = [
    # google_drive is no longer a placeholder — it has a real
    # PlatformConnector implementation (providers/google_drive/) registered
    # directly in bootstrap.py's IMPLEMENTED_PROVIDERS.
    ConnectorManifest(
        provider="onedrive", display_name="OneDrive", icon="☁️",
        category=ConnectorCategory.FILE_STORAGE, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
        supports_sync=True, supports_health_check=True,
        capabilities=(
            _cap("onedrive.list_files", "List files in the user's OneDrive", ("Files.Read",)),
            _cap("onedrive.read_file", "Read a file's content", ("Files.Read",)),
            _cap("onedrive.upload_file", "Upload a file", ("Files.ReadWrite",)),
        ),
    ),
    ConnectorManifest(
        provider="dropbox", display_name="Dropbox", icon="📦",
        category=ConnectorCategory.FILE_STORAGE, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
        supports_sync=True, supports_health_check=True,
        capabilities=(
            _cap("dropbox.list_files", "List files", ("files.metadata.read",)),
            _cap("dropbox.read_file", "Read a file's content", ("files.content.read",)),
            _cap("dropbox.upload_file", "Upload a file", ("files.content.write",)),
        ),
    ),
    ConnectorManifest(
        provider="sharepoint", display_name="SharePoint", icon="🏢",
        category=ConnectorCategory.FILE_STORAGE, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
        supports_sync=True, supports_health_check=True,
        capabilities=(
            _cap("sharepoint.list_sites", "List accessible SharePoint sites", ("Sites.Read.All",)),
            _cap("sharepoint.list_files", "List files in a document library", ("Files.Read.All",)),
        ),
    ),
    ConnectorManifest(
        provider="github", display_name="GitHub", icon="🐙",
        category=ConnectorCategory.CODE_REPO, auth_strategy_type=AuthStrategyType.API_KEY,
        supports_sync=True, supports_health_check=True,
        capabilities=(
            _cap("github.list_repos", "List the user's repositories", ("repo",)),
            _cap("github.read_file", "Read a file from a repo", ("repo",)),
            _cap("github.list_issues", "List issues in a repo", ("repo",)),
            _cap("github.create_pr", "Open a pull request", ("repo",)),
        ),
    ),
    ConnectorManifest(
        provider="gitlab", display_name="GitLab", icon="🦊",
        category=ConnectorCategory.CODE_REPO, auth_strategy_type=AuthStrategyType.API_KEY,
        supports_sync=True, supports_health_check=True,
        capabilities=(
            _cap("gitlab.list_projects", "List the user's projects", ("read_api",)),
            _cap("gitlab.read_file", "Read a file from a project", ("read_repository",)),
            _cap("gitlab.list_issues", "List issues in a project", ("read_api",)),
        ),
    ),
    ConnectorManifest(
        provider="notion", display_name="Notion", icon="📝",
        category=ConnectorCategory.KNOWLEDGE_BASE, auth_strategy_type=AuthStrategyType.API_KEY,
        supports_sync=True, supports_health_check=True,
        capabilities=(
            _cap("notion.list_pages", "List accessible pages"),
            _cap("notion.read_page", "Read a page's content"),
            _cap("notion.search", "Search across the workspace"),
        ),
    ),
    ConnectorManifest(
        provider="confluence", display_name="Confluence", icon="📘",
        category=ConnectorCategory.KNOWLEDGE_BASE, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
        supports_sync=True, supports_health_check=True,
        capabilities=(
            _cap("confluence.list_spaces", "List spaces", ("read:confluence-content.summary",)),
            _cap("confluence.read_page", "Read a page's content", ("read:confluence-content.all",)),
            _cap("confluence.search", "Search across spaces", ("read:confluence-content.summary",)),
        ),
    ),
    ConnectorManifest(
        provider="gmail", display_name="Gmail", icon="📧",
        category=ConnectorCategory.COMMUNICATION, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
        supports_sync=True, supports_health_check=True,
        capabilities=(
            _cap("gmail.list_messages", "List messages", ("gmail.readonly",)),
            _cap("gmail.read_message", "Read a message", ("gmail.readonly",)),
            _cap("gmail.send_message", "Send a message", ("gmail.send",)),
        ),
    ),
    ConnectorManifest(
        provider="google_calendar", display_name="Google Calendar", icon="📅",
        category=ConnectorCategory.CALENDAR, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
        supports_sync=True, supports_health_check=True,
        capabilities=(
            _cap("google_calendar.list_events", "List upcoming events", ("calendar.readonly",)),
            _cap("google_calendar.create_event", "Create an event", ("calendar.events",)),
        ),
    ),
    ConnectorManifest(
        provider="slack", display_name="Slack", icon="💬",
        category=ConnectorCategory.COMMUNICATION, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
        supports_sync=False, supports_health_check=True,
        capabilities=(
            _cap("slack.list_channels", "List channels", ("channels:read",)),
            _cap("slack.send_message", "Send a message to a channel", ("chat:write",)),
        ),
    ),
    ConnectorManifest(
        provider="teams", display_name="Microsoft Teams", icon="🟪",
        category=ConnectorCategory.COMMUNICATION, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
        supports_sync=False, supports_health_check=True,
        capabilities=(
            _cap("teams.list_channels", "List channels", ("ChannelSettings.Read.All",)),
            _cap("teams.send_message", "Send a channel message", ("ChannelMessage.Send",)),
        ),
    ),
    ConnectorManifest(
        provider="nas", display_name="NAS", icon="💾",
        category=ConnectorCategory.FILE_STORAGE, auth_strategy_type=AuthStrategyType.BASIC_AUTH,
        supports_sync=True, supports_health_check=True,
        capabilities=(
            _cap("nas.list_files", "List files on a mounted NAS share"),
            _cap("nas.read_file", "Read a file from a NAS share"),
        ),
    ),
    ConnectorManifest(
        provider="sftp", display_name="SFTP", icon="🔐",
        category=ConnectorCategory.FILE_STORAGE, auth_strategy_type=AuthStrategyType.SSH_KEY,
        supports_sync=True, supports_health_check=True,
        capabilities=(
            _cap("sftp.list_files", "List files on the remote server"),
            _cap("sftp.read_file", "Download a file's content"),
            _cap("sftp.upload_file", "Upload a file"),
        ),
    ),
    ConnectorManifest(
        provider="custom_rest", display_name="Custom REST API", icon="⚙️",
        category=ConnectorCategory.CUSTOM, auth_strategy_type=AuthStrategyType.CUSTOM_HEADER,
        supports_sync=False, supports_health_check=False,
        capabilities=(
            _cap("custom_rest.call", "Call a configured endpoint with user-supplied headers"),
        ),
    ),
]
