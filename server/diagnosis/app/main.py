import logging

from fastapi import FastAPI
from pydantic import ValidationError

from app.preparation.payload import DeviceDiagnosticReport
from app.preparation.ingestion import process_incoming_report

# Configure basic logging for the new service
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Diagnosis API",
    description="New device-centric diagnosis ingestion and execution service.",
    version="1.0.0",
)

@app.post("/api/v1/diagnosis/ingest")
async def ingest_report(report: DeviceDiagnosticReport):
    """
    HTTP endpoint to ingest a diagnostic report payload.
    In a production setup with MQTT, this logic would also be triggered by the MQTT consumer.
    """
    try:
        process_incoming_report(report)
        return {"status": "success", "message": "Report processed successfully"}
    except Exception as e:
        logger.error("Failed to process report: %s", str(e), exc_info=True)
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
