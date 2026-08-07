"""Escritura atómica de JSON para los archivos de memoria/estado en data/.

Sin esto, un crash o una escritura concurrente a mitad de camino deja el
archivo truncado; la próxima carga falla silenciosamente (except/pass) y el
siguiente save sobreescribe todo con el estado vacío, borrando la memoria
acumulada. temp file + os.replace hace que el archivo destino nunca quede
en un estado intermedio: o tiene el contenido viejo completo, o el nuevo.
"""
import json
import os
import tempfile


def atomic_write_json(path: str, data) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
