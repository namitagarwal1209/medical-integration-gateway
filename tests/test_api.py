#Automated tests for the API
#pip install pytest httpx
#pytest is a testing framework
#httpx allows FastAPI's test client to make requests to your application without starting a separate server.

#Run this on your terminal: python -m pytest tests/test_api.py -v

from fastapi.testclient import TestClient
from api import app, case_status

client = TestClient(app) #creates a test client to communicate with the FastAPI application

def test_home():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Medical Gateway Demo is running"}

def test_case_not_found():
    response = client.get("/cases/UNKNOWN/status") #sending patient id as UNKNOWN

    assert response.status_code == 200
    assert response.json() == {
        "patient_id": "UNKNOWN",
        "status": "NOT FOUND"           
    }

def test_case_exists():
    # Arrange: create a fake case
    case_status["TEST123"] = "COMPLETED"

    # Act: call the API
    response = client.get("/cases/TEST123/status")

    # Assert: verify the response
    assert response.status_code == 200

    assert response.json() == {
        "patient_id": "TEST123",
        "status": "COMPLETED"
    }

    # Cleanup
    del case_status["TEST123"]