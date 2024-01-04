def get_weather(location = "Yerevan"):
    '''Temperature in provided city(default Yerevan)'''
    return {
        "location": location,
        "temperature": "8C"
        }

get_weather_json = {
  "name": "get_weather",
  "parameters": {
    "type": "object",
    "properties": {
      "location": {
        "type": "string",
        "description": (
            "enter city for getting temperature"
        ),
      }
    },
    "required": [
      "location"
    ]
  },
  "description": "This function helps to get temperature in provided city"
}


