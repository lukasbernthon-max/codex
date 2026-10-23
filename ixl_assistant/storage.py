"""Only preferences are persisted in plaintext. Screenshots/history stay in RAM."""
import keyring

SERVICE = "FocusScreenshotAssistant"
ACCOUNT = "openai-api-key"


def load_key() -> str:
    return keyring.get_password(SERVICE, ACCOUNT) or ""


def save_key(value: str) -> None:
    if value.strip():
        keyring.set_password(SERVICE, ACCOUNT, value.strip())
    else:
        try:
            keyring.delete_password(SERVICE, ACCOUNT)
        except keyring.errors.PasswordDeleteError:
            pass
