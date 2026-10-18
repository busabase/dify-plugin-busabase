from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from busabase_dify.client import BusabaseClient, BusabaseError


class BusabaseProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """A cheap authenticated read: listing Bases needs only a read-level key."""
        try:
            BusabaseClient.from_credentials(credentials).list_bases()
        except BusabaseError as exc:
            raise ToolProviderCredentialValidationError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — surface anything else as a credential error too
            raise ToolProviderCredentialValidationError(f"Could not connect to Busabase: {exc}") from exc
