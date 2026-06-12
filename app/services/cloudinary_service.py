import os
import re


def cloudinary_configurato() -> bool:
    return bool(os.environ.get("CLOUDINARY_URL"))


def carica_immagine(contenuto: bytes, nome_file: str, folder: str = "lavori") -> str:
    import cloudinary.uploader  # type: ignore

    result = cloudinary.uploader.upload(
        contenuto,
        folder=folder,
        resource_type="image",
        use_filename=True,
        unique_filename=True,
    )
    return result["secure_url"]


def elimina_immagine(url: str) -> None:
    import cloudinary.uploader  # type: ignore

    # Estrae il public_id dall'URL, es:
    # https://res.cloudinary.com/cloud/image/upload/v123/lavori/5/foto.jpg
    # → public_id = "lavori/5/foto"
    match = re.search(r"/upload/(?:v\d+/)?(.+)\.[^.]+$", url)
    if match:
        public_id = match.group(1)
        cloudinary.uploader.destroy(public_id)
