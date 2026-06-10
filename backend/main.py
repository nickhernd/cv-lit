from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CV-Lit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development, adjust as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/dashboard")
def get_dashboard():
    return {
        "cameras_calibrated": 4,
        "total_cameras": 6,
        "images_processed": 506,
        "avg_dry_area": "23 480 m²",
        "cameras": [
            {"id": "C1", "name": "Norte", "status": "Calibrada", "images": 142},
            {"id": "C2", "name": "Norte Centro", "status": "Calibrada", "images": 138},
            {"id": "C3", "name": "Centro", "status": "Calibrada", "images": 96},
            {"id": "C4", "name": "Centro Sur", "status": "Sin calibrar", "images": 0},
            {"id": "C5", "name": "Sur", "status": "Calibrada", "images": 130},
            {"id": "C6", "name": "Sur Punta", "status": "Sin calibrar", "images": 12}
        ]
    }
