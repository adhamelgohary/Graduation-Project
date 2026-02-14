import os 
from utils.directory_configs import STATIC_FOLDER_ABS

def get_verfied_image_path(db_path: str , def_path: str) -> str:

    if not db_path:
        return def_path
    
    clean_db_path = db_path.replace("static/", "").lstrip("/")

    full_disk_path = os.path.join(STATIC_FOLDER_ABS, clean_db_path)
    
    if os.path.exists(full_disk_path):
        return clean_db_path
    
    return def_path
    