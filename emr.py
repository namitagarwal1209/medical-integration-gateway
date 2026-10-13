#port 8001

from fastapi import FastAPI, File, UploadFile
import os
app = FastAPI()

@app.get("/patient/{patient_id}/risk_factors")
def get_rfs(patient_id: str):
    return {
        "patient_id": patient_id,
        "smoking": True,
        "diabetes": False,
        "hypertension": False
    }


#ENDPOINT FOR EMR TO RECEIVE REPORT
@app.post("/patient/{patient_id}/report")
async def receive_report(patient_id: str,
                   file : UploadFile = File(...)):
    report_data = await file.read() #read the uploaded report file as bytes

    #save the received report
    os.makedirs("reports", exist_ok=True)

    file_path= f"reports/{patient_id}_report.pdf"
    with open(file_path, "wb") as f:
        f.write(report_data)


    return {
        "status": "Report Received",
        "filename": file.filename,
        "patient_id": patient_id,
        "report_received": True,
        "report_size": len(report_data)
    }