"""Private object storage used for durable sources and research artifacts."""

from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path


class ObjectStorage(ABC):
    @abstractmethod
    def upload_file(self, key: str, path: str | Path, *, content_type: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def download_file(self, key: str, path: str | Path) -> None:
        raise NotImplementedError

    @abstractmethod
    def open_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def exists(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> None:
        raise NotImplementedError


class LocalObjectStorage(ObjectStorage):
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    def upload_file(self, key: str, path: str | Path, *, content_type: str | None = None) -> None:
        del content_type
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)

    def download_file(self, key: str, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self._path(key), destination)

    def open_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class AzureBlobStorage(ObjectStorage):
    def __init__(self, connection_string: str, container: str):
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient.from_connection_string(connection_string)
        self.container = service.get_container_client(container)

    def upload_file(self, key: str, path: str | Path, *, content_type: str | None = None) -> None:
        from azure.storage.blob import ContentSettings

        settings = ContentSettings(content_type=content_type) if content_type else None
        with Path(path).open("rb") as stream:
            self.container.upload_blob(
                name=key, data=stream, overwrite=True, content_settings=settings
            )

    def download_file(self, key: str, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as stream:
            self.container.download_blob(key).readinto(stream)

    def open_bytes(self, key: str) -> bytes:
        return self.container.download_blob(key).readall()

    def exists(self, key: str) -> bool:
        return self.container.get_blob_client(key).exists()

    def delete(self, key: str) -> None:
        self.container.delete_blob(key, delete_snapshots="include")


def get_storage() -> ObjectStorage:
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    if backend == "local":
        return LocalObjectStorage(os.getenv("LOCAL_STORAGE_ROOT", "./storage"))
    if backend == "azure":
        connection = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection:
            raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is required")
        return AzureBlobStorage(connection, os.getenv("AZURE_STORAGE_CONTAINER", "poligrapher"))
    raise RuntimeError(f"Unsupported STORAGE_BACKEND: {backend}")


def source_key(policy_id, filename: str) -> str:
    safe_name = Path(filename).name or "source.pdf"
    return f"sources/{policy_id}/{safe_name}"


def artifact_key(policy_id, *, failed: bool = False) -> str:
    suffix = "failure" if failed else "artifacts"
    return f"artifacts/{policy_id}/{suffix}.zip"
