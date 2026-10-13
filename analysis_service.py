
from fastapi import FastAPI
from fastapi.responses import Response
from reportlab.pdfgen import canvas
from io import BytesIO

app = FastAPI(title="Medical Analysis Service")


# Endpoint for receiving cases and returning analysis results
@app.post("/cases")
def receive_case(case: dict):

    print(f"Received case: {case}")

    return {
        "case_id": case["case_id"],
        "status": "analysis_complete",
        "result": {
            "risk": "moderate",
            "plaque_detected": True
        },
        "report_url": f"http://localhost:8002/reports/{case['case_id']}.pdf"
    }


# Endpoint for generating a PDF report
@app.get("/reports/{case_id}.pdf")
def get_report(case_id: str):

    pdf = BytesIO()
    c = canvas.Canvas(pdf)

    c.drawString(100, 750, f"Medical Analysis Report for Case ID: {case_id}")
    c.drawString(100, 730, "Risk Level: moderate")
    c.drawString(100, 710, "Plaque Detected: True")

    c.showPage()
    c.save()

    pdf.seek(0)

    return Response(
        content=pdf.getvalue(),
        media_type="application/pdf"
    )
