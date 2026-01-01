# Pharmacy Agent
In this project I have created a agent that acts as a pharmacist assistant. 
This agent can be used to query information about:
- Medication doses and uses.
- Prescription requierments for medication.
- Availability of the medication at the store.
- Reservation of medication, and cancellation of reservations.
- User prescriptions and reservations.

## Agent Flow:
User -> Agent -> Tools -> Agent -> Response  
With perhaps multiple calls to tools.

## Running the agent:
Its quite simple - download the repo, and then run docker:
```
# Build the Docker image
docker build -t wonderful-backend .

# Set your API Key (Windows PowerShell)
$env:OPENAI_API_KEY="sk-..."

# Run the container
docker run --rm -p 8000:8000 -e OPENAI_API_KEY=$env:OPENAI_API_KEY wonderful-backend
```

### Running the client:
You have two options.  
  Either a browser based chat style UI.
  To Run:
  - Open the frontend/index.html file with Live Server, or use any simple static server.
  - Ensure the connection URL in the UI is set to ws://localhost:8000/ws.
    
  Or, Console interface.
  From the project root run:
```
python frontend/ws.py
``` 
## To run the eval tests from the root run:
```
# Set your openai API key
$env:OPENAI_API_KEY="Openai-api-key"

# Map the background directory to your python path, so it can import app, etc.
$env:PYTHONPATH="backend"

# Run the tests
python backend/eval/run_eval.py
```
## To run the tool tests run:
from the backend folder:
```
pytest -q 
```
Have fun.








