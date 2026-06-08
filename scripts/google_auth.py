"""
Autenticação OAuth 2.0 com conta Google do usuário (fluxo desktop).

O token fica em credentials/token.json — nunca commitar.
"""

from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Leitura de planilhas + metadados Drive para localizar backends AppSheet.
ESCOPOS = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def obter_credenciais(pasta_credenciais: Path) -> Credentials:
    """
    Carrega ou renova credenciais OAuth.

    Na primeira execução abre o navegador para login Google.
    """
    pasta_credenciais.mkdir(parents=True, exist_ok=True)
    caminho_token = pasta_credenciais / "token.json"
    caminho_client = pasta_credenciais / "client_secret.json"

    if not caminho_client.is_file():
        raise FileNotFoundError(
            f"Arquivo {caminho_client} ausente. Siga SETUP.md para criar OAuth no Google Cloud."
        )

    credenciais: Credentials | None = None
    if caminho_token.is_file():
        credenciais = Credentials.from_authorized_user_file(str(caminho_token), ESCOPOS)

    if not credenciais or not credenciais.valid:
        if credenciais and credenciais.expired and credenciais.refresh_token:
            credenciais.refresh(Request())
        else:
            fluxo = InstalledAppFlow.from_client_secrets_file(str(caminho_client), ESCOPOS)
            credenciais = fluxo.run_local_server(port=0, open_browser=True)
        caminho_token.write_text(credenciais.to_json(), encoding="utf-8")

    return credenciais


def criar_servico_sheets(credenciais: Credentials):
    """Retorna cliente Google Sheets API v4."""
    return build("sheets", "v4", credentials=credenciais, cache_discovery=False)


def criar_servico_drive(credenciais: Credentials):
    """Retorna cliente Google Drive API v3."""
    return build("drive", "v3", credentials=credenciais, cache_discovery=False)
