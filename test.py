from dotenv import load_dotenv
from openai import OpenAI
import os
load_dotenv()

client = OpenAI(
    # This is the default and can be omitted
    api_key=os.environ.get("API_KEY")

)

def generate_description(file_contents, current_description):
    prompt = f"""
    Here is the current description of the repository:

    {current_description}

    Here are the contents of the repository files:

    {file_contents}

    Based on the above, please provide a concise and informative description for this repository.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Replace with "gpt-3.5-turbo" if needed
            messages=[
                {"role": "system", "content": "You are a helpful assistant that writes repository descriptions."},
                {"role": "user", "content": prompt}
            ]
        )
        description = response.choices[0].message.content
        return description
    except Exception as e:
        print(f"Error generating description: {e}")
        return None
    
print(generate_description("say test", "say test"))