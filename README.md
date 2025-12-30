# Pharmacy Agent
In this project I have created a agent that acts as a pharmacist assistant. 
This agent can be used to query information about:
- Medication doses and uses.
- Prescription requierments for medication.
- Availability of the medication at the store.
- Reservation of medication, and cancellation of reservations.
- User prescriptions and reservations.
  
## The project includes the following files:
- main.py
- agent.py
- tools.py
- inventory.json
- medications.json
- users.json 
## Tools
This agent has access to the following tools:
- 

## Using the agent:
Its quite simple - download the repo, add your api key to a .env file and then run docker. 
```
docker build -t wonderful-backend .
$env:OPENAI_API_KEY="sk-..."
docker run --rm -p 8000:8000 -e OPENAI_API_KEY=$env:OPENAI_API_KEY wonderful-backend
```
Have fun.

