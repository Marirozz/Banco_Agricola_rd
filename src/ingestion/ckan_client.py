"""Cliente mínimo para el API CKAN de datos.gob.do.

No requiere autenticación: el portal expone metadatos y descargas de forma
pública vía /api/3/action/package_show.
"""
import hashlib
import json
import os
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CKAN_BASE_URL = "https://datos.gob.do"
PACKAGE_SHOW_ENDPOINT = f"{CKAN_BASE_URL}/api/3/action/package_show"
REQUEST_TIMEOUT = 30


class CkanDatasetError(RuntimeError):
    """Error al resolver o descargar un dataset/recurso de CKAN."""


def build_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_package(session, package_id):
    try:
        response = session.get(
            PACKAGE_SHOW_ENDPOINT, params={"id": package_id}, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CkanDatasetError(f"No se pudo consultar el paquete '{package_id}': {exc}") from exc

    payload = response.json()
    if not payload.get("success"):
        raise CkanDatasetError(f"CKAN respondió sin éxito para el paquete '{package_id}'.")
    return payload["result"]


def select_resource(package, fmt):
    fmt = fmt.upper()
    for resource in package.get("resources", []):
        if resource.get("format", "").upper() == fmt:
            return resource
    raise CkanDatasetError(
        f"El paquete '{package.get('name', package.get('id'))}' no tiene un recurso en formato {fmt}."
    )


def sha256_of_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_resource(session, resource, dest_path):
    try:
        response = session.get(resource["url"], timeout=REQUEST_TIMEOUT, stream=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CkanDatasetError(f"No se pudo descargar el recurso '{resource.get('id')}': {exc}") from exc

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    tmp_path = dest_path + ".part"
    with open(tmp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    os.replace(tmp_path, dest_path)


def load_manifest(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(path, manifest):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, sort_keys=True)


def utcnow_iso():
    return datetime.now(timezone.utc).isoformat()
