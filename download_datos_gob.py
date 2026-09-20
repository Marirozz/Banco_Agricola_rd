"""Descarga los datasets financieros de BAGRICOLA publicados en datos.gob.do.

Consulta el API de CKAN por cada dataset y sólo descarga cuando el portal
reporta un `last_modified` distinto al de la última corrida (registrado en
data/raw/financial/manifest.json). Guarda el archivo vigente con el nombre
base que espera src/extract_financial.py, y conserva además una copia
histórica con fecha en data/raw/financial/history/.

Preferencia de formato: XLSX primero; si el recurso no existe o el archivo
publicado no se puede leer (algunos vienen en OOXML "Strict", no soportado
por openpyxl), se cae a CSV. ODS nunca se descarga.

Uso:
    python download_datos_gob.py                   # descarga solo lo que cambió
    python download_datos_gob.py --force            # fuerza la descarga de todo
    python download_datos_gob.py --dataset cartera  # sincroniza solo un dataset
"""
import argparse
import logging
import os
import shutil
import sys

import pandas as pd

from src.ingestion.ckan_client import (
    CkanDatasetError,
    build_session,
    download_resource,
    fetch_package,
    load_manifest,
    save_manifest,
    select_resource,
    sha256_of_file,
    utcnow_iso,
)
from src.ingestion.datasets_config import ALLOWED_EXTENSIONS, DATASETS, HISTORY_DIR, MANIFEST_PATH, RAW_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _read_csv_flexible(path, **kwargs):
    """CKAN CSV exports from this portal use ';' as separator and are
    encoded as Windows-1252 (Excel 'ANSI' export), not UTF-8 or comma-CSV."""
    kwargs.setdefault("sep", ";")
    try:
        return pd.read_csv(path, encoding="utf-8-sig", **kwargs)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="cp1252", **kwargs)


def validate_resource_shape(path, fmt, expected_columns):
    try:
        if fmt.upper() == "CSV":
            df = _read_csv_flexible(path, nrows=5)
        else:
            df = pd.read_excel(path, nrows=5)
    except Exception as exc:
        raise CkanDatasetError(f"No se pudo abrir el archivo descargado '{path}': {exc}") from exc

    if len(df.columns) != expected_columns:
        raise CkanDatasetError(
            f"'{path}' tiene {len(df.columns)} columnas, se esperaban {expected_columns}. "
            "El portal pudo haber cambiado el formato del archivo — revisar antes de usarlo."
        )


def _remove_if_exists(path):
    if os.path.exists(path):
        os.remove(path)


def _cleanup_other_formats(basename, keep_extension):
    for ext in ALLOWED_EXTENSIONS:
        if ext != keep_extension:
            _remove_if_exists(os.path.join(RAW_DIR, f"{basename}.{ext}"))


def sync_dataset(session, dataset, manifest, force):
    key = dataset["key"]
    logger.info("Revisando dataset '%s'...", key)

    try:
        package = fetch_package(session, dataset["package_id"])
    except CkanDatasetError as exc:
        logger.error("No se pudo consultar el dataset '%s': %s", key, exc)
        return False

    previous = manifest.get(key, {})

    for fmt in dataset["formats"]:
        try:
            resource = select_resource(package, fmt)
        except CkanDatasetError:
            logger.info("El dataset '%s' no publica un recurso en formato %s. Probando el siguiente.", key, fmt)
            continue

        # El portal ha mezclado por error el recurso de un dataset con el
        # archivo de otro (p. ej. el XLSX de "desembolsos" apunta al archivo
        # de "cartera"). La URL del recurso conserva el nombre real del
        # archivo, así que la usamos para detectar ese caso antes de bajarlo.
        if dataset["target_basename"] not in (resource.get("url") or ""):
            logger.warning(
                "El recurso %s en formato %s del dataset '%s' no corresponde al archivo esperado "
                "(url=%s) — probablemente un error de publicación en el portal. Se omite.",
                resource.get("id"), fmt, key, resource.get("url"),
            )
            continue

        remote_last_modified = resource.get("last_modified") or resource.get("created")

        if not force and previous.get("format") == fmt and previous.get("last_modified") == remote_last_modified:
            logger.info("'%s' sin cambios (formato=%s, last_modified=%s). Se omite la descarga.", key, fmt, remote_last_modified)
            return True

        extension = fmt.lower()
        target_path = os.path.join(RAW_DIR, f"{dataset['target_basename']}.{extension}")

        try:
            download_resource(session, resource, target_path)
            validate_resource_shape(target_path, fmt, dataset["expected_columns"])
        except CkanDatasetError as exc:
            logger.warning("Formato %s falló para '%s': %s. Probando el siguiente formato preferido.", fmt, key, exc)
            _remove_if_exists(target_path)
            continue

        _cleanup_other_formats(dataset["target_basename"], keep_extension=extension)

        file_hash = sha256_of_file(target_path)
        pulled_at = utcnow_iso()

        if previous.get("sha256") != file_hash:
            os.makedirs(HISTORY_DIR, exist_ok=True)
            history_path = os.path.join(HISTORY_DIR, f"{key}_{pulled_at[:10]}.{extension}")
            shutil.copyfile(target_path, history_path)
            logger.info("Snapshot histórico guardado en: %s", history_path)
        else:
            logger.info("'%s' descargado, pero el contenido es idéntico al último pull.", key)

        manifest[key] = {
            "resource_id": resource.get("id"),
            "format": fmt,
            "last_modified": remote_last_modified,
            "sha256": file_hash,
            "local_path": target_path,
            "pulled_at": pulled_at,
        }
        logger.info("'%s' actualizado correctamente (%s) -> %s", key, fmt, target_path)
        return True

    logger.error("Ningún formato preferido (%s) funcionó para '%s'.", dataset["formats"], key)
    return False


def main():
    parser = argparse.ArgumentParser(description="Descarga los datasets financieros de BAGRICOLA desde datos.gob.do")
    parser.add_argument("--force", action="store_true", help="Descarga aunque no se detecten cambios")
    parser.add_argument("--dataset", choices=[d["key"] for d in DATASETS], help="Sincroniza solo un dataset")
    args = parser.parse_args()

    datasets = [d for d in DATASETS if args.dataset in (None, d["key"])]
    manifest = load_manifest(MANIFEST_PATH)
    session = build_session()

    results = [sync_dataset(session, dataset, manifest, args.force) for dataset in datasets]
    save_manifest(MANIFEST_PATH, manifest)

    if not all(results):
        logger.error("Uno o más datasets fallaron. Revisa el log arriba.")
        sys.exit(1)

    logger.info("Sincronización completada.")


if __name__ == "__main__":
    main()
