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

## Using the agent:
Its quite simple - download the repo, and then run docker:
```
docker build -t wonderful-backend .
$env:OPENAI_API_KEY="sk-..."
docker run --rm -p 8000:8000 -e OPENAI_API_KEY=$env:OPENAI_API_KEY wonderful-backend
```
You can use the index.html file in the frontend for a nicer experience.
## To run the eval tests from the root run:
```
$env:OPENAI_API_KEY="Openai-api-key"
$env:PYTHONPATH="backend"
python backend/eval/run_eval.py
```
## To run the tool tests run:
from the backend folder:
```
pytest -q 
```
Have fun.






