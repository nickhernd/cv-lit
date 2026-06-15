import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCES_IMAGES_DIR = os.path.join(BASE_DIR, "proces_images")
DATA_DIR = os.path.join(PROCES_IMAGES_DIR, "data")
CALIBRATION_DIR = os.path.join(BASE_DIR, "calibration")

CAMERAS = {
    1: {"name": "CAM 1 (Norte)", "id": "8213", "serial": "PTM61471",
        "folder": "CAM_1/images", "file": "1779787800_20260526_093000_PTM61471.jpg"},
    2: {"name": "CAM 2 (Norte Centro)", "id": "8214", "serial": "PTM61474",
        "folder": "CAM_2/images", "file": "1778580900_20260512_101500_PTM61474.jpg"},
    3: {"name": "CAM 3 (Centro)", "id": "8212", "serial": "PTM61473",
        "folder": "CAM_3/images", "file": "1777896000_20260504_120000_PTM61473.jpg"},
    4: {"name": "CAM 4 (Centro Sur)", "id": "8211", "serial": "PTM61475",
        "folder": "CAM_4/images", "file": "1777896000_20260504_120000_PTM61475.jpg"},
    5: {"name": "CAM 5 (Sur)", "id": "8209", "serial": "PTM61472",
        "folder": "CAM_5/images", "file": "1777893600_20260504_112000_PTM61472.jpg"},
    6: {"name": "CAM 6 (Sur Punta)", "id": "8210", "serial": "PTM61470",
        "folder": "CAM_6/images", "file": "1777891200_20260504_104000_PTM61470.jpg"},
}
