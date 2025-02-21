from fastapi import FastAPI, Depends, Cookie, Response, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
import re
from mistralai import Mistral
import uuid
from fastapi.middleware.cors import CORSMiddleware
import os

# Config
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

nemo_model = "open-mistral-nemo"
model = "mistral-large-latest"


# Interfaces
class KeywordParseRequest(BaseModel):
    input: str
    session_id: str


class TripRequest(BaseModel):
    days: int
    startDate: str
    city: str
    country: str
    choices: list


app = FastAPI()
origins = [
    "http://localhost:3000",  # Frontend origin
    "https://pocket-japan-fastapi-hackathon.vercel.app",
    "https://pocket-japan.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


client = Mistral(api_key=MISTRAL_API_KEY)

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

    conversation_history = conversation_histories.get(
        session_id,
        [
            {
                "role": "system",
                "content": """
            You are an agent that identifies key travel plan information from the user-provided information.
            You need to infer the country code by yourself. If all information is recognized, please ignore the user's original
            question and return a JSON output that includes 'city', 'country', 'countryCode', 'days', 'startDate', and exit the loop.
            If any information is missing, prompt the user for the missing details (DO NOT mention JSON).
            Please DO NOT repeatedly ask for the information the user has already provided!
            If the user mentions an x-days plan, it means that the user is going to stay x days somewhere.
            The default year should be 2024 if the user did not mention.
            Please infer the country from the city by yourself; if you cannot, please ask the user which country it is.
            Please DO NOT ask the user about the country code; please infer it from the country according to the Google GL Parameter.
            The JSON format should be:
            ```json
            {\
              "city": string,
              "country": string,
              "countryCode": string,
              "days": int (number),
              "startDate": "YYYY-MM-dd"
            }
            ```
            """,
            }
        ],
    )

    print(conversation_history)

    # Add user's input to the conversation history
    conversation_history.append({"role": "user", "content": user_input})

    try:
        # Call the Mistral API
        chat_response = client.chat.complete(model=model, messages=conversation_history)

        if chat_response is None or not chat_response.choices:
            raise HTTPException(
                status_code=500, detail="Failed to get a response from the assistant"
            )

        # Extract the assistant's response
        response_content = chat_response.choices[0].message.content.strip()

        # Add assistant's response to the conversation history
        conversation_history.append({"role": "assistant", "content": response_content})

        # Save the updated conversation history
        conversation_histories[session_id] = conversation_history

        # Set the session ID cookie
        response.set_cookie(key="session_id", value=session_id)

        # Try to extract JSON from the assistant's response
        json_match = re.search(r"```json\n({.*?})\n```", response_content, re.DOTALL)

        if json_match:
            try:
                json_string = json_match.group(1)
                extracted_info = json.loads(json_string)
                print
                return extracted_info
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to extract JSON from the assistant's response",
                )
        else:
            # Return the assistant's response text
            return {"response": response_content, "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occured: {e}")

@app.post("/itinerary")
async def PlanItinerary(data: TripRequest, response: Response):
    print(data)
    # Destructure data
    
    system_message = {
        "role": "system",
        "content": (
            """
            "You will receive a JSON file containing multiple items. Each item includes keywords such as 'category' (e.g., activity/lunch/dinner),'title','rating','address','operating hours', and 'discription'. In addition to the JSON file, you will also be given the number of travel days and the starting date. "
            "First, you need to summarize the discription and the rating for each item. Then, based on the number of travel days, the starting date, and the summary you made, you will create a travel plan for the user. "
            "The travel plan should include: 'date', 'starting time', 'end time', 'title', and 'description' (which is the summary you made). "
            "Ensure that each day includes lunch and dinner activities. "
            "When planning each place, you need to consider the address of each title and the commute time from title to title. Try to avoid scheduling two titles that are far apart consecutively, and make sure to account for commute time in the starting time and ending time. Each interval between itineraries should not exceed one hour. "
            "Each title's description should be around 50 words. "
             The output should be:
            ```json
            {\
                "itineraryItems": [
                    {
                        "day": X,
                        "dates": "YYYY-MM-DD",
                        "city": "City Name",
                        "image": "image URL from the json",
                        "slots": [
                        {
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {
                            "startTime": "HH:MM AM/PM",
                            "endTime": "HH:MM AM/PM"
                            },
                            "description": "Description of the place",
                        },
                        {
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {
                            "startTime": "HH:MM AM/PM",
                            "endTime": "HH:MM AM/PM"
                            },
                            "description": "Description of the place",
                        }
                        ]
                    },
                    {
                        "day": X,
                        "dates": "YYYY-MM-DD",
                        "city": "City Name",
                        "image": "image URL from the json",
                        "slots": [
                        {
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {
                            "startTime": "HH:MM AM/PM",
                            "endTime": "HH:MM AM/PM"
                            },
                            "description": "Description of the place",
                        },
                        {
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {
                            "startTime": "HH:MM AM/PM",
                            "endTime": "HH:MM AM/PM"
                            },
                            "description": "Description of the place",
                        }
                        ]
                    }
                    
                ]            
            }
            ```
            """
        )
    }

    user_content_template = (
        f"This is a {data.days} day trip starting from {data.startDate}, and the JSON file is {data.choices}"
    )



    try:
        chat_response = client.chat.complete(
            model=nemo_model,
            messages=[
                system_message,
                {
                    "role": "user",
                    "content": user_content_template,
                },
            ],
        )

        if chat_response is None or not chat_response.choices:
            raise HTTPException(
                status_code=500, detail="Failed to get a response from the assistant"
            )
        print(chat_response)
        # Extract the assistant's response
        response_content = chat_response.choices[0].message.content.strip()

        # Try to extract JSON from the assistant's response
        json_match = re.search(r"```json\n({.*?})\n```", response_content, re.DOTALL)

        if json_match:
            try:
                json_string = json_match.group(1)
                extracted_info = json.loads(json_string)
                return extracted_info
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to extract JSON from the assistant's response",
                )
        else:
            # Return the assistant's response text
            return {"response": response_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occured: {e}")



@app.post("/itinerary-slim")
async def PlanItinerary(data: TripRequest, response: Response):
    print(data)
    # Destructure data
    
    system_message = {
        "role": "system",
        "content": (
            """
            "You will receive a JSON file containing multiple items. Each item includes keywords such as 'category' (e.g., activity/lunch/dinner),'title','rating','address','operating hours', and 'discription'. In addition to the JSON file, you will also be given the number of travel days and the starting date. "
            "First, you need to summarize the description and the rating for each item. Then, based on the number of travel days, the starting date, and the summary you made, you will create a travel plan for the user. "
            "The travel plan should include: 'date', 'starting time', 'end time', 'title', and 'description' (which is the summary you made). "
            "Ensure that each day includes lunch and dinner activities. "
            "Limit the number of slots of each day to 3. "
            "Each title's description should be around 10 words. "
             The output should be:
            ```json
            {\
                "itineraryItems": [
                    {
                        "day": 1,
                        "dates": "2024-10-01",
                        "city": "Tokyo",
                        "image": thumbnail,
                        "slots": [
                        {
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {
                            "startTime": "09:00 AM",
                            "endTime": "10:30 AM"
                            },
                            "description": "Description of the place",
                        },
                        {
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {
                            "startTime": "11:00 AM",
                            "endTime": "12:30 PM"
                            },
                            "description": "Description of the place",
                        }
                        ]
                    },
                    {
                        "day": 2,
                        "dates": "2024-10-02",
                        "city": "Tokyo",
                        "image": "thumbnail",
                        "slots": [
                        {
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {
                            "startTime": "01:00 PM",
                            "endTime": "02:30 PM"
                            },
                            "description": "Description of the place",
                        }
                        ]
                    }
                ]            
            }
            ```
            """
        )
    }

    user_content_template = (
        f"This is a {data.days} day trip starting from {data.startDate}, and the JSON file is {data.choices}"
    )



    try:
        chat_response = client.chat.complete(
            model=model,
            messages=[
                system_message,
                {
                    "role": "user",
                    "content": user_content_template,
                },
            ],
        )

        if chat_response is None or not chat_response.choices:
            raise HTTPException(
                status_code=500, detail="Failed to get a response from the assistant"
            )
        print(chat_response)
        # Extract the assistant's response
        response_content = chat_response.choices[0].message.content.strip()

        # Try to extract JSON from the assistant's response
        json_match = re.search(r"```json\n({.*?})\n```", response_content, re.DOTALL)

        if json_match:
            try:
                json_string = json_match.group(1)
                extracted_info = json.loads(json_string)
                return extracted_info
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to extract JSON from the assistant's response",
                )
        else:
            # Return the assistant's response text
            return {"response": response_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occured: {e}")

@app.post("/itinerary-mini")
async def PlanItinerary(data: TripRequest, response: Response):
    print(data)
    # Destructure data
    
    system_message = {
        "role": "system",
        "content": (
            """
            "You will receive a JSON file containing multiple items. Each item includes keywords such as 'category' (e.g., activity/lunch/dinner),'title','rating','address','operating hours', and 'discription'. In addition to the JSON file, you will also be given the number of travel days and the starting date. "
            "First, you need to summarize the discription and the rating for each item. Then, based on the number of travel days, the starting date, and the summary you made, you will create a travel plan for the user. "
            "The travel plan should include: 'date', 'starting time', 'end time', 'title', and 'description' (which is the summary you made). "
            "Ensure that each day includes lunch and dinner activities. "
            "Limit the number of slots of each day to 3. "
            "Each title's description should be around 10 words. "
             The output should be:
            ```json
            {\
                "itineraryItems": [
                    {
                        "day": 1,
                        "dates": "2024-10-01",
                        "city": "Tokyo",
                        "image": thumbnail,
                        "slots": [
                        {
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {
                            "startTime": "09:00 AM",
                            "endTime": "10:30 AM"
                            },
                            "description": "Description of the place",
                        },
                        {
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {
                            "startTime": "11:00 AM",
                            "endTime": "12:30 PM"
                            },
                            "description": "Description of the place",
                        }
                        ]
                    },
                    {
                        "day": 2,
                        "dates": "2024-10-02",
                        "city": "Tokyo",
                        "image": "thumbnail",
                        "slots": [
                        {
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {
                            "startTime": "01:00 PM",
                            "endTime": "02:30 PM"
                            },
                            "description": "Description of the place",
                        }
                        ]
                    }
                ]            
            }
            ```
            """
        )
    }

    user_content_template = (
        f"This is a {data.days} day trip starting from {data.startDate}, and the JSON file is {data.choices}"
    )



    try:
        chat_response = client.chat.complete(
            model=model,
            messages=[
                system_message,
                {
                    "role": "user",
                    "content": user_content_template,
                },
            ],
        )

        if chat_response is None or not chat_response.choices:
            raise HTTPException(
                status_code=500, detail="Failed to get a response from the assistant"
            )
        print(chat_response)
        # Extract the assistant's response
        response_content = chat_response.choices[0].message.content.strip()

        # Try to extract JSON from the assistant's response
        json_match = re.search(r"```json\n({.*?})\n```", response_content, re.DOTALL)

        if json_match:
            try:
                json_string = json_match.group(1)
                extracted_info = json.loads(json_string)
                return extracted_info
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to extract JSON from the assistant's response",
                )
        else:
            # Return the assistant's response text
            return {"response": response_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occured: {e}")


@app.post("/itinerary-changed")
async def PlanItinerary(data: TripRequest, response: Response):
    print(data)
    # Destructure data
    
    system_message = {
        "role": "system",
        "content": (
            """
            "You will receive a JSON file containing multiple items. Each item includes keywords such as 'category' (e.g., activity/lunch/dinner),'title','rating','address','operating hours', and 'discription'. In addition to the JSON file, you will also be given the number of travel days and the starting date. "
            "First, you need to summarize the discription and the rating for each item. Then, based on the number of travel days, the starting date, and the summary you made, you will create a travel plan for the user. "
            "The travel plan should include: 'date', 'starting time', 'end time', 'title', and 'description' (which is the summary you made). "
            "Ensure that each day includes lunch and dinner activities. "
            "Before you generate the final json file, you need to make sure each interval between itineraries should not exceed one hour. Please add internal json element with key timeIntervals with all the intervals to double-check. "
            "Each title's description should be around 50 words. "
             The output should be:
            ```json
            {\
                "itineraryItems": [
                    {
                        "day": 1,
                        "dates": "2024-10-01",
                        "city": "Tokyo",
                        "image": thumbnail,
                        "slots": [
                        {
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {
                            "startTime": "09:00 AM",
                            "endTime": "10:30 AM"
                            },
                            "description": "Description of the place",
                        },
                        {
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {
                            "startTime": "11:00 AM",
                            "endTime": "12:30 PM"
                            },
                            "description": "Description of the place",
                        }
                        ]
                    },
                    {
                        "day": 2,
                        "dates": "2024-10-02",
                        "city": "Tokyo",
                        "image": "thumbnail",
                        "slots": [
                        {
                            "data_id": "data_id",
                            "location": "Title of the place",
                            "time": {
                            "startTime": "01:00 PM",
                            "endTime": "02:30 PM"
                            },
                            "description": "Description of the place",
                        }
                        ]
                    }
                ]            
            }
            ```
            """
        )
    }

    user_content_template = (
        f"This is a {data.days} day trip starting from {data.startDate}, and the JSON file is {data.choices}"
    )



    try:
        chat_response = client.chat.complete(
            model=model,
            messages=[
                system_message,
                {
                    "role": "user",
                    "content": user_content_template,
                },
            ],
        )

        if chat_response is None or not chat_response.choices:
            raise HTTPException(
                status_code=500, detail="Failed to get a response from the assistant"
            )
        print(chat_response)
        # Extract the assistant's response
        response_content = chat_response.choices[0].message.content.strip()

        # Try to extract JSON from the assistant's response
        json_match = re.search(r"```json\n({.*?})\n```", response_content, re.DOTALL)

        if json_match:
            try:
                json_string = json_match.group(1)
                extracted_info = json.loads(json_string)
                return extracted_info
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to extract JSON from the assistant's response",
                )
        else:
            # Return the assistant's response text
            return {"response": response_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occured: {e}")


