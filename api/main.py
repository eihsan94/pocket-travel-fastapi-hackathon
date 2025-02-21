# main.py

from fastapi import FastAPI, Depends, Cookie, Response, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import json
import re
import openai
import uuid
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from dotenv import load_dotenv
# Config
load_dotenv()  # Load environment variables from .env file

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set.")
openai.api_key = OPENAI_API_KEY

# Model configurations
model = "gpt-4o"

# Set up logging
logging.basicConfig(level=logging.INFO)

# Interfaces
class KeywordParseRequest(BaseModel):
    input: str
    session_id: Optional[str] = None

class TripRequest(BaseModel):
    days: int = 1  # Default to 1 day if not provided
    city: str
    country: str
    choices: List[dict]
    start_time: Optional[str] = None  # New field for start time
    end_time: Optional[str] = None    # New field for end time
    end_location: Optional[str] = None  # New field for end location
    preferences: Optional[str] = None  # New field for user preferences
    language: Optional[str] = None  # New field for language

app = FastAPI()
origins = [
    "http://localhost:3000",  # Frontend origin
    "https://pocket-japan-fastapi-hackathon.vercel.app",
    "https://pocket-japan-hackathon.vercel.app",
    "https://pocket-japan.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conversation_histories = {}

async def get_session_id(session_id: Optional[str] = Cookie(default=None)):
    if session_id is None:
        session_id = str(uuid.uuid4())
    return session_id

@app.post("/keyword-search")
async def KeywordParse(
    data: KeywordParseRequest,
    response: Response,
    session_id: str = Depends(get_session_id),
):
    session_id = data.session_id if data.session_id else session_id
    user_input = data.input

    # System prompt instructing the AI to detect the language automatically
    conversation_history = conversation_histories.get(
        session_id,
        [
            {
                "role": "system",
                "content": """
                You are an agent that identifies key travel plan information from the user-provided input.
                Detect the language of the user's query and respond in the same language.
                If all required information is recognized, ignore the user's original question and return a JSON output
                that includes:
                - 'city'
                - 'country'
                - 'countryCode'
                - 'days' (default to 1 if not specified)
                - 'start_time' (if specified)
                - 'end_time' (if specified)
                - 'end_location' (if specified)
                - 'preferences' (if specified)
                - 'language' (the detected language name in English, e.g., 'English', 'Japanese')

                Assume a 1-day trip if the user does not specify the number of days. Do not ask for this information unless explicitly stated by the user.

                If any information is missing, prompt the user for the missing details without mentioning JSON format.
                - Do not repeatedly ask for information the user has already provided.
                - If the user mentions an x-day plan, it means that they intend to stay x days in a location.
                - Use 2024 as the default year if none is specified by the user.
                - Try to infer the country from the city; if unable, ask the user which country it is.
                - Do not ask the user for the country code; infer it from the country according to the Google GL Parameter.

                The response format should be in JSON, as follows:
                ```json
                {{
                  "city": string,
                  "country": string,
                  "countryCode": string,
                  "days": int,
                  "start_time": string (if specified),
                  "end_time": string (if specified),
                  "end_location": string (if specified),
                  "preferences": string (if specified),
                  "language": string
                }}
                """
            }
        ],
    )

    conversation_history.append({"role": "user", "content": user_input})

    try:
        logging.info("Calling OpenAI API for keyword parsing")
        chat_response = openai.chat.completions.create(
            model=model,
            messages=conversation_history,
        )

        if not chat_response.choices:
            logging.error("No response from OpenAI API")
            raise HTTPException(
                status_code=500, detail="Failed to get a response from the assistant"
            )

        response_content = chat_response.choices[0].message.content.strip()
        conversation_history.append({"role": "assistant", "content": response_content})
        conversation_histories[session_id] = conversation_history
        response.set_cookie(key="session_id", value=session_id)

        json_match = re.search(r"```json\n({.*?})\n```", response_content, re.DOTALL)

        if json_match:
            try:
                json_string = json_match.group(1)
                extracted_info = json.loads(json_string)
                return extracted_info
            except json.JSONDecodeError as json_err:
                logging.error("JSON decode error: %s", json_err)
                raise HTTPException(
                    status_code=500, detail="Failed to parse JSON response from assistant",
                )
        else:
            return {"response": response_content, "session_id": session_id}
    except openai.APIError as api_err:
        logging.error("OpenAI API error: %s", api_err)
        raise HTTPException(
            status_code=500, detail="An error occurred with the OpenAI API",
        )
    except Exception as e:
        logging.error("Unexpected error: %s", e)
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {e}"
        )

# Adjusted itinerary endpoint without the start date
@app.post("/itinerary")
async def PlanItinerary(data: TripRequest, response: Response):
    system_message = {
        "role": "system",
        "content": """
            Detect the language of the user's input and respond in the same language.

            You will receive a JSON file containing multiple items. Each item includes:
            - 'category' (e.g., activity, lunch, dinner)
            - 'title'
            - 'rating'
            - 'address'
            - 'operating hours'
            - 'description'

            You will also receive the number of travel days, a specific start time, end time, end location, and any user preferences if provided.

            Plan the itinerary within the specified timeframe and end at the specified location if provided.
            If the user mentions a start time or end time, adjust activities to fit within this window.
            Summarize the description and rating for each item, and organize the activities within the time constraints.

            Additional Instructions:
            - Ensure that each day includes lunch and dinner activities.
            - Consider the address and commute time between locations, avoiding scheduling locations that are far apart consecutively.
            - Make sure to account for commute time in the starting and ending times.
            - Each interval between activities should not exceed one hour.
            - Limit each title's description to around 50 words.
            - Only include activities that match the user's preferences (e.g., indoor activities).

            The output should be:
            ```json
            {{
                "itineraryItems": [
                    {{
                        "day": X,
                        "dates": "YYYY-MM-DD",
                        "city": "City Name",
                        "image": "image URL from the json",
                        "slots": [
                        {{
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {{
                            "startTime": "HH:MM AM/PM",
                            "endTime": "HH:MM AM/PM"
                            }},
                            "description": "Description of the place",
                            "language": "the detected language name in English, e.g., 'English', 'Japanese'"
                        }},
                        {{
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {{
                            "startTime": "HH:MM AM/PM",
                            "endTime": "HH:MM AM/PM"
                            }},
                            "description": "Description of the place",
                            "language": "the detected language name in English, e.g., 'English', 'Japanese'"
                        }}
                        ]
                    }}
                ]            
            }}
            """
    }

    user_content_template = (
        f"This is a {data.days} day trip in {data.city}."
        + (f" The start time is {data.start_time}." if data.start_time else "")
        + (f" The end time is {data.end_time}." if data.end_time else "")
        + (f" The itinerary should end at {data.end_location}." if data.end_location else "")
        + (f" The user preferences are: {data.preferences}." if data.preferences else "")
        + f" The JSON file is {data.choices}."
    )
    logging.info("User content template: %s", user_content_template)
    try:
        logging.info("Calling OpenAI API for itinerary planning")
        chat_response = openai.chat.completions.create(
            model=model,
            messages=[
                system_message,
                {"role": "user", "content": user_content_template},
            ],
        )

        if not chat_response.choices:
            logging.error("No response from OpenAI API")
            raise HTTPException(
                status_code=500, detail="Failed to get a response from the assistant"
            )

        response_content = chat_response.choices[0].message.content.strip()
        json_match = re.search(r"```json\n({.*?})\n```", response_content, re.DOTALL)

        if json_match:
            try:
                json_string = json_match.group(1)
                extracted_info = json.loads(json_string)
                return extracted_info
            except json.JSONDecodeError as json_err:
                logging.error("JSON decode error: %s", json_err)
                raise HTTPException(
                    status_code=500,
                    detail="Failed to parse JSON response from assistant",
                )
        else:
            return {"response": response_content}
    except openai.APIError as api_err:
        logging.error("OpenAI API error: %s", api_err)
        raise HTTPException(
            status_code=500,
            detail="An error occurred with the OpenAI API",
        )
    except Exception as e:
        logging.error("Unexpected error: %s", e)
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {e}"
        )
