#port 8000

#fastAPI - creates your web app
# UploadFile is FastAPI's object for handling uploaded files
# File is used to indicate that the endpoint expects a file upload


#CONFIGURATION
#pip install python-dotenv    ----  This library allows Python to load environment variables from a .env file. 

from fastapi import FastAPI, UploadFile, File
import os
import requests
import pydicom
from io import BytesIO
import logging
from dotenv import load_dotenv


load_dotenv()  # Load environment variables from .env file
EMR_URL = os.getenv("EMR_URL")
ANALYSIS_SERVICE_URL = os.getenv("ANALYSIS_SERVICE_URL")
ORTHANC_URL = os.getenv("ORTHANC_URL")
ORTHANC_USERNAME = os.getenv("ORTHANC_USERNAME")
ORTHANC_PASSWORD = os.getenv("ORTHANC_PASSWORD")


app = FastAPI() # Medical Gateway application

#set up the default logging configuration
logging.basicConfig(
    level=logging.INFO, #show me INFO and above messages
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("med_gateway") #logger object called med_gateway

case_status={} #to track the status of each case (e.g., whether it has been sent to analysis_service and Orthanc)

UPLOAD_DIR = "incoming"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
def home():
    return {"message": "Medical Gateway Demo is running"}

# Get the status of a specific case by patient ID
@app.get("/cases/{patient_id}/status")
def get_case_status(patient_id: str):
    return {
        "patient_id": patient_id, 
        "status": case_status.get(patient_id, "NOT FOUND")}

######GET RFS FROM EMR SERVER#############
def get_rfs(patient_id):
    try:
        response =  requests.get(
            f"{EMR_URL}/patient/{patient_id}/risk_factors",
            timeout=5
        )
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

        return response.json()
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Case {patient_id}: EMR request failed: {e}")
        return None
#########################################

# Process DICOM upload and coordinate integration services
@app.post("/upload-dicom")
async def upload_dicom(file: UploadFile = File(...)): 

#file: UploadFile means I accept a file called file
# = File(...) means File type. (...) means the file is required
#async because I am using await to read the file asynchronously

    file_data = await file.read() #file_data is raw bytes

    #read the DICOM file into a pydicom dataset object
    ds = pydicom.dcmread(BytesIO(file_data))

    ##GET RFS FROM EMR SERVER##
    patient_id = str(ds.PatientID)
    case_status[patient_id] = "RECEIVED SCAN"

    #calls EMR to retrieve risk factors
    rfs = get_rfs(patient_id)

    if rfs is None:
        case_status[patient_id] = "ERROR_RETRIEVING_RF"
        return {
            "patient_id": patient_id,
            "error": "ERROR_RETRIEVING_RF"
        }
    
    logger.info(f"Retrieved risk factors for patient {patient_id}")

    case_status[patient_id] = "RECEIVED SCAN RF"
    

    ##SEND CASE AND RFS TO analysis_service. RECEIVE RESPONSE FROM analysis_service##
    case = {
        "case_id" : patient_id,
        "risk_factors": rfs
    }

    try:
        analysis_response = requests.post(f"{ANALYSIS_SERVICE_URL}/cases", 
                                           json=case,
                                           timeout=10) #send python dict as JSON to analysis_service
        analysis_response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

    except requests.exceptions.RequestException as e:

        logger.error(f"Case {patient_id}: Error sending case to analysis_service: {e}")

        case_status[patient_id] = "ERROR_SENDING_TO_ANALYSIS_SERVICE"
        return {
            "patient_id": patient_id,
            "error": "ERROR_SENDING_TO_ANALYSIS_SERVICE"
        }

    logger.info(f"Case {patient_id} sent to analysis_service")
    case_status[patient_id] = "SENT_TO_ANALYSIS_SERVICE"

    analysis_result = analysis_response.json()
    logger.info(f"analysis_service response received for case {patient_id}")

    #Extracting report
    report_url = f"{ANALYSIS_SERVICE_URL}/reports/{patient_id}.pdf" #URL to fetch the PDF report from analysis_service

    try:
        report_response = requests.get(
            report_url,
            timeout=10) #fetches the PDF report from analysis_service

        report_response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
        report_data = report_response.content #retrieves the PDF content as bytes

        logger.info(f"Report received from analysis_service for case {patient_id}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Case {patient_id}: Error fetching report from analysis_service: {e}")
        
        case_status[patient_id] = "ERROR_FETCHING_REPORT"
        return {
            "patient_id": patient_id,
            "error": "ERROR_FETCHING_REPORT"
        }

    case_status[patient_id] = "REPORT_RECEIVED"

    #Send report to EMR server
    try:
        report_response_emr = requests.post(
            f"{EMR_URL}/patient/{patient_id}/report",
            files={    #send a file to the EMR server
                "file":(
                    f"{patient_id}_report.pdf", #filename
                    report_data, #PDF content as bytes
                    "application/pdf" #MIME type for PDF files
                )
            },
            timeout=10
        )
        report_response_emr.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
        case_status[patient_id] = "REPORT_SENT_TO_EMR: COMPLETED"

    except requests.exceptions.RequestException as e:
        logger.error(f"Case {patient_id}: Error sending report to EMR: {e}")
        case_status[patient_id] = "ERROR_SENDING_REPORT_TO_EMR"
        return {
            "patient_id": patient_id,
            "error": "ERROR_SENDING_REPORT_TO_EMR"
        }
            
    logger.info(f"EMR report response for case {patient_id}: {report_response_emr.json()}")
    logger.info(f"Case {patient_id}: report delivered to EMR")
    logger.info(f"Case {patient_id}: processing completed")


    ###########DEIDENTIFY##################
    #DEIDENTIFYING the DICOM dataset by removing sensitiveinformation
    ds.PatientName = "Anonymous"
    ds.PatientBirthDate = ""
    ds.PatientSex = ""

    #convert modified DICOM dataset back to bytes
    output = BytesIO() #creates empty file-like object for the deidentified DICOM data
    ds.save_as(output) #saves the deidentified DICOM data 

    deidentified_file_data = output.getvalue() #retreives the deidentified DICOM data as bytes

    #######################################

    

    #8042 is the port number for the Orthanc server
    #we use 'requests' to send the DICOM file to the Orthanc server
    try:
        response = requests.post(f"{ORTHANC_URL}/instances",
                                 data=deidentified_file_data,
                                 headers={"Content-Type": "application/dicom"},
                                 auth=(ORTHANC_USERNAME, ORTHANC_PASSWORD),
                                 timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

    except requests.exceptions.RequestException as e:
        logger.error(f"Case {patient_id}: Error sending deidentified DICOM to Orthanc: {e}")
        case_status[patient_id] = "ERROR_SENDING_DEIDENTIFIED_DICOM_TO_ORTHANC"
        return {
            "patient_id": patient_id,
            "error": "ERROR_SENDING_DEIDENTIFIED_DICOM_TO_ORTHANC"
        }
    
    case_status[patient_id] = "DEIDENTIFIED_DICOM_SENT_TO_ORTHANC"

    return {
        "message": "DICOM sent to Orthanc",
        "filename": file.filename,
        "original_patient_name": "REDACTED",
        "new_patient_name": str(ds.PatientName),
        "study_instance_uid": str(ds.StudyInstanceUID),
        "modality": str(ds.Modality),
        "Smoking": rfs.get("smoking"),
        "Diabetes": rfs.get("diabetes"),
        "Hypertension": rfs.get("hypertension"),
        "orthanc_status":response.status_code,
        "analysis_service_response": analysis_result
    }